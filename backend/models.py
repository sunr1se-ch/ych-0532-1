from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Pool(Base):
    __tablename__ = "pools"

    id = Column(Integer, primary_key=True, index=True)
    pool_number = Column(String, unique=True, index=True, nullable=False)
    pump_number = Column(String, unique=True, index=True, nullable=False)
    max_capacity = Column(Integer, nullable=False)
    current_count = Column(Integer, default=0)
    is_isolation = Column(Boolean, default=False)
    pump_status = Column(String, default="normal")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    oxygen_readings = relationship("OxygenReading", back_populates="pool", cascade="all, delete-orphan")
    source_transfers = relationship("TransferRecord", foreign_keys="TransferRecord.source_pool_id", back_populates="source_pool")
    target_transfers = relationship("TransferRecord", foreign_keys="TransferRecord.target_pool_id", back_populates="target_pool")


class OxygenReading(Base):
    __tablename__ = "oxygen_readings"

    id = Column(Integer, primary_key=True, index=True)
    pool_id = Column(Integer, ForeignKey("pools.id"), nullable=False)
    reading = Column(Float, nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())

    pool = relationship("Pool", back_populates="oxygen_readings")


class TransferRecord(Base):
    __tablename__ = "transfer_records"

    id = Column(Integer, primary_key=True, index=True)
    source_pool_id = Column(Integer, ForeignKey("pools.id"), nullable=False)
    target_pool_id = Column(Integer, ForeignKey("pools.id"), nullable=False)
    fish_count = Column(Integer, nullable=False)
    reason = Column(String, default="疾病隔离")
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())

    source_pool = relationship("Pool", foreign_keys=[source_pool_id], back_populates="source_transfers")
    target_pool = relationship("Pool", foreign_keys=[target_pool_id], back_populates="target_transfers")
