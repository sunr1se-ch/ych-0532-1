from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class PoolBase(BaseModel):
    pool_number: str
    pump_number: str
    max_capacity: int
    current_count: int = 0
    is_isolation: bool = False
    pump_status: str = "normal"


class PoolCreate(PoolBase):
    pass


class Pool(PoolBase):
    id: int
    created_at: datetime
    isolation_used: Optional[int] = 0
    isolation_full: Optional[bool] = False

    class Config:
        from_attributes = True


class OxygenReadingBase(BaseModel):
    pool_id: int
    reading: float


class OxygenReadingCreate(OxygenReadingBase):
    pass


class OxygenReading(OxygenReadingBase):
    id: int
    recorded_at: datetime

    class Config:
        from_attributes = True


class TransferRecordBase(BaseModel):
    source_pool_id: int
    target_pool_id: int
    fish_count: int
    reason: str = "疾病隔离"


class TransferRecordCreate(TransferRecordBase):
    pass


class TransferRecord(TransferRecordBase):
    id: int
    recorded_at: datetime
    source_pool_number: Optional[str] = None
    target_pool_number: Optional[str] = None

    class Config:
        from_attributes = True


class TransferResponse(BaseModel):
    success: bool
    message: str
    data: Optional[TransferRecord] = None


class PoolDetail(Pool):
    oxygen_readings: List[OxygenReading] = []
    transfer_records: List[TransferRecord] = []


class PoolStatusSummary(BaseModel):
    normal_count: int
    maintenance_count: int
    isolation_full_count: int
    total_pools: int
