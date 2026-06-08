from sqlalchemy.orm import Session
from database import engine, SessionLocal
import models
from datetime import datetime, timedelta
import random

models.Base.metadata.create_all(bind=engine)

db = SessionLocal()

try:
    existing_pools = db.query(models.Pool).count()
    if existing_pools > 0:
        print("数据库已存在数据，跳过初始化")
        exit(0)

    pools_data = [
        {"pool_number": "A-01", "pump_number": "P-101", "max_capacity": 50, "current_count": 35, "is_isolation": False},
        {"pool_number": "A-02", "pump_number": "P-102", "max_capacity": 50, "current_count": 42, "is_isolation": False},
        {"pool_number": "A-03", "pump_number": "P-103", "max_capacity": 60, "current_count": 28, "is_isolation": False},
        {"pool_number": "B-01", "pump_number": "P-201", "max_capacity": 40, "current_count": 38, "is_isolation": False},
        {"pool_number": "B-02", "pump_number": "P-202", "max_capacity": 40, "current_count": 0, "is_isolation": False},
        {"pool_number": "C-01", "pump_number": "P-301", "max_capacity": 30, "current_count": 15, "is_isolation": True},
        {"pool_number": "C-02", "pump_number": "P-302", "max_capacity": 20, "current_count": 8, "is_isolation": True},
    ]

    created_pools = []
    for pool_data in pools_data:
        pool = models.Pool(**pool_data)
        db.add(pool)
        created_pools.append(pool)
    db.commit()

    for pool in created_pools:
        db.refresh(pool)

    now = datetime.now()
    pool_readings = {}
    for pool in created_pools:
        readings = []
        for h in range(24, 0, -1):
            record_time = now - timedelta(hours=h)
            if pool.pool_number == "A-02":
                if h <= 2:
                    reading_val = round(random.uniform(3.2, 3.9), 1)
                else:
                    reading_val = round(random.uniform(5.5, 7.8), 1)
            elif pool.pool_number == "B-01":
                reading_val = round(random.uniform(4.0, 5.0), 1)
            else:
                reading_val = round(random.uniform(5.5, 8.0), 1)

            readings.append(models.OxygenReading(
                pool_id=pool.id,
                reading=reading_val,
                recorded_at=record_time
            ))
        db.bulk_save_objects(readings)
        pool_readings[pool.id] = readings
    db.commit()

    for pool in created_pools:
        recent = db.query(models.OxygenReading).filter(
            models.OxygenReading.pool_id == pool.id
        ).order_by(models.OxygenReading.recorded_at.desc()).limit(2).all()
        if len(recent) >= 2 and recent[0].reading < 4 and recent[1].reading < 4:
            pool.pump_status = "maintenance"
            db.commit()

    display_pools = [p for p in created_pools if not p.is_isolation]
    isolation_pools = [p for p in created_pools if p.is_isolation]

    transfer_times = [
        now - timedelta(days=5, hours=3),
        now - timedelta(days=3, hours=8),
        now - timedelta(days=1, hours=14),
    ]

    transfers_data = [
        {"source": "A-01", "target": "C-01", "count": 3, "reason": "白点病隔离", "time": transfer_times[0]},
        {"source": "A-03", "target": "C-01", "count": 2, "reason": "水霉病隔离", "time": transfer_times[1]},
        {"source": "B-01", "target": "C-02", "count": 4, "reason": "烂鳃病隔离", "time": transfer_times[2]},
    ]

    for t_data in transfers_data:
        source = next(p for p in created_pools if p.pool_number == t_data["source"])
        target = next(p for p in created_pools if p.pool_number == t_data["target"])

        transfer = models.TransferRecord(
            source_pool_id=source.id,
            target_pool_id=target.id,
            fish_count=t_data["count"],
            reason=t_data["reason"],
            recorded_at=t_data["time"]
        )
        db.add(transfer)
        source.current_count -= t_data["count"]
        target.current_count += t_data["count"]

    db.commit()
    print("数据库初始化完成，演示数据已导入")
    print(f"共创建 {len(created_pools)} 个池位")
    print(f"共生成 {24 * len(created_pools)} 条溶氧读数记录")
    print(f"共创建 {len(transfers_data)} 条转移记录")

except Exception as e:
    print(f"初始化失败: {e}")
    db.rollback()
finally:
    db.close()
