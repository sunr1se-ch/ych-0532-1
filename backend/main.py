from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from datetime import datetime, timedelta
from typing import List, Optional
import models
import schemas
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="水族馆溶氧泵与隔离转移登记系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def check_pump_status(db: Session, pool_id: int):
    recent_readings = db.query(models.OxygenReading).filter(
        models.OxygenReading.pool_id == pool_id
    ).order_by(desc(models.OxygenReading.recorded_at)).limit(2).all()

    if len(recent_readings) >= 2:
        if recent_readings[0].reading < 4 and recent_readings[1].reading < 4:
            pool = db.query(models.Pool).filter(models.Pool.id == pool_id).first()
            if pool and pool.pump_status != "maintenance":
                pool.pump_status = "maintenance"
                db.commit()
                return True
    return False


def get_isolation_usage(db: Session, pool_id: int) -> int:
    seven_days_ago = datetime.now() - timedelta(days=7)
    result = db.query(func.sum(models.TransferRecord.fish_count)).filter(
        models.TransferRecord.target_pool_id == pool_id,
        models.TransferRecord.recorded_at >= seven_days_ago
    ).scalar()
    return result or 0


def get_recently_transferred_count(db: Session, pool_id: int) -> int:
    seven_days_ago = datetime.now() - timedelta(days=7)
    result = db.query(func.sum(models.TransferRecord.fish_count)).filter(
        models.TransferRecord.source_pool_id == pool_id,
        models.TransferRecord.recorded_at >= seven_days_ago
    ).scalar()
    return result or 0


def enrich_pool(db: Session, pool: models.Pool) -> schemas.Pool:
    isolation_used = get_isolation_usage(db, pool.id)
    pool_data = schemas.Pool.model_validate(pool)
    pool_data.isolation_used = isolation_used
    pool_data.isolation_full = pool.is_isolation and isolation_used >= pool.max_capacity
    return pool_data


@app.get("/api/pools", response_model=List[schemas.Pool])
def get_pools(db: Session = Depends(get_db)):
    pools = db.query(models.Pool).all()
    return [enrich_pool(db, pool) for pool in pools]


@app.get("/api/pools/status-summary", response_model=schemas.PoolStatusSummary)
def get_pools_status_summary(db: Session = Depends(get_db)):
    total = db.query(models.Pool).count()
    maintenance = db.query(models.Pool).filter(models.Pool.pump_status == "maintenance").count()
    normal_count = db.query(models.Pool).filter(
        models.Pool.pump_status == "normal",
        models.Pool.is_isolation == False
    ).count()

    pools = db.query(models.Pool).filter(models.Pool.is_isolation == True).all()
    isolation_full = 0
    for pool in pools:
        usage = get_isolation_usage(db, pool.id)
        if usage >= pool.max_capacity:
            isolation_full += 1

    return schemas.PoolStatusSummary(
        normal_count=normal_count,
        maintenance_count=maintenance,
        isolation_full_count=isolation_full,
        total_pools=total
    )


@app.get("/api/pools/maintenance", response_model=List[schemas.Pool])
def get_maintenance_pools(db: Session = Depends(get_db)):
    pools = db.query(models.Pool).filter(models.Pool.pump_status == "maintenance").all()
    return [enrich_pool(db, pool) for pool in pools]


@app.post("/api/pools", response_model=schemas.Pool)
def create_pool(pool: schemas.PoolCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Pool).filter(
        (models.Pool.pool_number == pool.pool_number) |
        (models.Pool.pump_number == pool.pump_number)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="池号或泵编号已存在")

    db_pool = models.Pool(**pool.model_dump())
    db.add(db_pool)
    db.commit()
    db.refresh(db_pool)
    return enrich_pool(db, db_pool)


@app.get("/api/pools/{pool_id}", response_model=schemas.PoolDetail)
def get_pool_detail(pool_id: int, db: Session = Depends(get_db)):
    pool = db.query(models.Pool).filter(models.Pool.id == pool_id).first()
    if not pool:
        raise HTTPException(status_code=404, detail="池不存在")

    readings = db.query(models.OxygenReading).filter(
        models.OxygenReading.pool_id == pool_id
    ).order_by(models.OxygenReading.recorded_at).all()

    transfers = db.query(models.TransferRecord).filter(
        (models.TransferRecord.source_pool_id == pool_id) |
        (models.TransferRecord.target_pool_id == pool_id)
    ).order_by(desc(models.TransferRecord.recorded_at)).all()

    transfer_list = []
    for t in transfers:
        t_data = schemas.TransferRecord.model_validate(t)
        t_data.source_pool_number = t.source_pool.pool_number
        t_data.target_pool_number = t.target_pool.pool_number
        transfer_list.append(t_data)

    pool_data = enrich_pool(db, pool)
    return schemas.PoolDetail(
        **pool_data.model_dump(),
        oxygen_readings=readings,
        transfer_records=transfer_list
    )


@app.post("/api/oxygen-readings", response_model=schemas.OxygenReading)
def create_oxygen_reading(reading: schemas.OxygenReadingCreate, db: Session = Depends(get_db)):
    pool = db.query(models.Pool).filter(models.Pool.id == reading.pool_id).first()
    if not pool:
        raise HTTPException(status_code=404, detail="池不存在")

    db_reading = models.OxygenReading(**reading.model_dump())
    db.add(db_reading)
    db.commit()
    db.refresh(db_reading)

    check_pump_status(db, reading.pool_id)

    return db_reading


@app.get("/api/pools/{pool_id}/oxygen-readings", response_model=List[schemas.OxygenReading])
def get_pool_oxygen_readings(
    pool_id: int,
    hours: int = Query(24, description="查询最近多少小时的数据"),
    db: Session = Depends(get_db)
):
    pool = db.query(models.Pool).filter(models.Pool.id == pool_id).first()
    if not pool:
        raise HTTPException(status_code=404, detail="池不存在")

    time_cutoff = datetime.now() - timedelta(hours=hours)
    readings = db.query(models.OxygenReading).filter(
        models.OxygenReading.pool_id == pool_id,
        models.OxygenReading.recorded_at >= time_cutoff
    ).order_by(models.OxygenReading.recorded_at).all()

    return readings


@app.get("/api/transfer-records", response_model=List[schemas.TransferRecord])
def get_transfer_records(
    source_pool_id: Optional[int] = None,
    target_pool_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.TransferRecord)
    if source_pool_id:
        query = query.filter(models.TransferRecord.source_pool_id == source_pool_id)
    if target_pool_id:
        query = query.filter(models.TransferRecord.target_pool_id == target_pool_id)

    transfers = query.order_by(desc(models.TransferRecord.recorded_at)).all()
    result = []
    for t in transfers:
        t_data = schemas.TransferRecord.model_validate(t)
        t_data.source_pool_number = t.source_pool.pool_number
        t_data.target_pool_number = t.target_pool.pool_number
        result.append(t_data)
    return result


@app.post("/api/transfer-records", response_model=schemas.TransferResponse)
def create_transfer_record(transfer: schemas.TransferRecordCreate, db: Session = Depends(get_db)):
    source_pool = db.query(models.Pool).filter(models.Pool.id == transfer.source_pool_id).first()
    target_pool = db.query(models.Pool).filter(models.Pool.id == transfer.target_pool_id).first()

    if not source_pool:
        return schemas.TransferResponse(success=False, message="源池不存在")
    if not target_pool:
        return schemas.TransferResponse(success=False, message="目标隔离池不存在")

    if not target_pool.is_isolation:
        return schemas.TransferResponse(success=False, message="目标池不是隔离池")

    if source_pool.is_isolation:
        return schemas.TransferResponse(success=False, message="隔离池不能作为转出源池，请从展示池登记转移")

    if source_pool.pump_status == "maintenance":
        return schemas.TransferResponse(success=False, message="源池关联泵待检修，禁止新鱼入池操作")

    if transfer.fish_count <= 0:
        return schemas.TransferResponse(success=False, message="转移尾数必须大于0")

    if source_pool.current_count < transfer.fish_count:
        return schemas.TransferResponse(
            success=False,
            message=f"源池当前尾数({source_pool.current_count})不足，无法转移{transfer.fish_count}尾"
        )

    isolation_used = get_isolation_usage(db, target_pool.id)
    if isolation_used + transfer.fish_count > target_pool.max_capacity:
        return schemas.TransferResponse(
            success=False,
            message=f"目标隔离池7天内借隔离容量已满(已用{isolation_used}/上限{target_pool.max_capacity})，禁止转入"
        )

    recently_transferred = get_recently_transferred_count(db, source_pool.id)
    if recently_transferred + transfer.fish_count > source_pool.max_capacity:
        return schemas.TransferResponse(
            success=False,
            message=f"源池7天内已转移{recently_transferred}尾，同一尾鱼7天内不得二次转移"
        )

    db_transfer = models.TransferRecord(**transfer.model_dump())
    db.add(db_transfer)

    source_pool.current_count -= transfer.fish_count
    target_pool.current_count += transfer.fish_count

    db.commit()
    db.refresh(db_transfer)

    t_data = schemas.TransferRecord.model_validate(db_transfer)
    t_data.source_pool_number = source_pool.pool_number
    t_data.target_pool_number = target_pool.pool_number

    return schemas.TransferResponse(
        success=True,
        message="转移登记成功",
        data=t_data
    )


@app.put("/api/pools/{pool_id}/pump-status", response_model=schemas.Pool)
def update_pump_status(
    pool_id: int,
    status: str = Query(..., description="normal 或 maintenance"),
    db: Session = Depends(get_db)
):
    pool = db.query(models.Pool).filter(models.Pool.id == pool_id).first()
    if not pool:
        raise HTTPException(status_code=404, detail="池不存在")

    if status not in ["normal", "maintenance"]:
        raise HTTPException(status_code=400, detail="状态只能是 normal 或 maintenance")

    pool.pump_status = status
    db.commit()
    db.refresh(pool)
    return enrich_pool(db, pool)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
