"""
SQLAlchemy ORM 模型定义
"""

from datetime import datetime
from typing import Optional, Dict, Any
import json
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import relationship

Base = declarative_base()


class JSONEncodedDict(TypeDecorator):
    """JSON 编码字典类型"""
    impl = Text

    def process_bind_param(self, value: Optional[Dict[str, Any]], dialect):
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value: Optional[str], dialect):
        if value is None:
            return None
        return json.loads(value)


class Account(Base):
    """已注册账号表"""
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password = Column(String(255))  # 注册密码（明文存储）
    access_token = Column(Text)
    refresh_token = Column(Text)
    id_token = Column(Text)
    session_token = Column(Text)  # 会话令牌（优先刷新方式）
    client_id = Column(String(255))  # OAuth Client ID
    account_id = Column(String(255))
    workspace_id = Column(String(255))
    email_service = Column(String(50), nullable=False)  # 'tempmail', 'outlook', 'custom_domain'
    email_service_id = Column(String(255))  # 邮箱服务中的ID
    proxy_used = Column(String(255))
    registered_at = Column(DateTime, default=datetime.utcnow)
    last_refresh = Column(DateTime)  # 最后刷新时间
    expires_at = Column(DateTime)  # Token 过期时间
    status = Column(String(20), default='active')  # 'active', 'expired', 'banned', 'failed'
    extra_data = Column(JSONEncodedDict)  # 额外信息存储
    cpa_uploaded = Column(Boolean, default=False)  # 是否已上传到 CPA
    cpa_uploaded_at = Column(DateTime)  # 上传时间
    source = Column(String(20), default='register')  # 'register' 或 'login'，区分账号来源
    subscription_type = Column(String(20))  # None / 'plus' / 'team'
    subscription_at = Column(DateTime)  # 订阅开通时间
    cookies = Column(Text)  # 完整 cookie 字符串，用于支付请求
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'email': self.email,
            'password': self.password,
            'client_id': self.client_id,
            'email_service': self.email_service,
            'account_id': self.account_id,
            'workspace_id': self.workspace_id,
            'registered_at': self.registered_at.isoformat() if self.registered_at else None,
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'status': self.status,
            'proxy_used': self.proxy_used,
            'cpa_uploaded': self.cpa_uploaded,
            'cpa_uploaded_at': self.cpa_uploaded_at.isoformat() if self.cpa_uploaded_at else None,
            'source': self.source,
            'subscription_type': self.subscription_type,
            'subscription_at': self.subscription_at.isoformat() if self.subscription_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class EmailService(Base):
    """邮箱服务配置表"""
    __tablename__ = 'email_services'

    id = Column(Integer, primary_key=True, autoincrement=True)
    service_type = Column(String(50), nullable=False)  # 'outlook', 'custom_domain'
    name = Column(String(100), nullable=False)
    config = Column(JSONEncodedDict, nullable=False)  # 服务配置（加密存储）
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # 使用优先级
    last_used = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RegistrationTask(Base):
    """注册任务表"""
    __tablename__ = 'registration_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_uuid = Column(String(36), unique=True, nullable=False, index=True)  # 任务唯一标识
    status = Column(String(20), default='pending')  # 'pending', 'running', 'completed', 'failed', 'cancelled'
    email_service_id = Column(Integer, ForeignKey('email_services.id'), index=True)  # 使用的邮箱服务
    proxy = Column(String(255))  # 使用的代理
    logs = Column(Text)  # 注册过程日志
    result = Column(JSONEncodedDict)  # 注册结果
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # 关系
    email_service = relationship('EmailService')


class Setting(Base):
    """系统设置表"""
    __tablename__ = 'settings'

    key = Column(String(100), primary_key=True)
    value = Column(Text)
    description = Column(Text)
    category = Column(String(50), default='general')  # 'general', 'email', 'proxy', 'openai'
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CpaService(Base):
    """CPA 服务配置表"""
    __tablename__ = 'cpa_services'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # 服务名称
    api_url = Column(String(500), nullable=False)  # API URL
    api_token = Column(Text, nullable=False)  # API Token
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # 优先级
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Sub2ApiService(Base):
    """Sub2API 服务配置表"""
    __tablename__ = 'sub2api_services'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # 服务名称
    api_url = Column(String(500), nullable=False)  # API URL (host)
    api_key = Column(Text, nullable=False)  # x-api-key
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # 优先级
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TeamManagerService(Base):
    """Team Manager 服务配置表"""
    __tablename__ = 'tm_services'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # 服务名称
    api_url = Column(String(500), nullable=False)  # API URL
    api_key = Column(Text, nullable=False)  # X-API-Key
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # 优先级
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Proxy(Base):
    """代理列表表"""
    __tablename__ = 'proxies'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # 代理名称
    type = Column(String(20), nullable=False, default='http')  # http, socks5
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(100))
    password = Column(String(255))
    enabled = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # 是否为默认代理
    priority = Column(Integer, default=0)  # 优先级（保留字段）
    last_used = Column(DateTime)  # 最后使用时间
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, include_password: bool = False) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'enabled': self.enabled,
            'is_default': self.is_default or False,
            'priority': self.priority,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_password:
            result['password'] = self.password
        else:
            result['has_password'] = bool(self.password)
        return result

    @property
    def proxy_url(self) -> str:
        """获取完整的代理 URL"""
        if self.type == "http":
            scheme = "http"
        elif self.type == "socks5":
            scheme = "socks5"
        else:
            scheme = self.type

        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"

        return f"{scheme}://{auth}{self.host}:{self.port}"


class ScheduledTask(Base):
    """定时任务表"""
    __tablename__ = 'scheduled_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)  # 任务名称
    hour = Column(Integer, nullable=False, default=3)  # 执行时（0-23）
    minute = Column(Integer, nullable=False, default=0)  # 执行分（0-59）
    email_service_type = Column(String(50), nullable=False, default='tempmail')
    email_service_id = Column(Integer)  # 指定邮箱服务 ID（可选）
    count = Column(Integer, nullable=False, default=10)  # 注册数量
    concurrency = Column(Integer, nullable=False, default=5)  # 并发数
    mode = Column(String(20), nullable=False, default='pipeline')  # parallel / pipeline
    interval_min = Column(Integer, default=5)
    interval_max = Column(Integer, default=30)
    proxy = Column(String(255))  # 代理设置
    auto_upload_cpa = Column(Boolean, default=False)
    cpa_service_ids = Column(JSONEncodedDict)  # JSON list
    auto_upload_sub2api = Column(Boolean, default=False)
    sub2api_service_ids = Column(JSONEncodedDict)  # JSON list
    sub2api_group_id = Column(String(255))  # Sub2API 分组 ID
    auto_upload_tm = Column(Boolean, default=False)
    tm_service_ids = Column(JSONEncodedDict)  # JSON list
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime)
    next_run_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'hour': self.hour,
            'minute': self.minute,
            'email_service_type': self.email_service_type,
            'email_service_id': self.email_service_id,
            'count': self.count,
            'concurrency': self.concurrency,
            'mode': self.mode,
            'interval_min': self.interval_min,
            'interval_max': self.interval_max,
            'proxy': self.proxy,
            'auto_upload_cpa': self.auto_upload_cpa,
            'cpa_service_ids': self.cpa_service_ids or [],
            'auto_upload_sub2api': self.auto_upload_sub2api,
            'sub2api_service_ids': self.sub2api_service_ids or [],
            'sub2api_group_id': self.sub2api_group_id,
            'auto_upload_tm': self.auto_upload_tm,
            'tm_service_ids': self.tm_service_ids or [],
            'enabled': self.enabled,
            'last_run_at': self.last_run_at.isoformat() if self.last_run_at else None,
            'next_run_at': self.next_run_at.isoformat() if self.next_run_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ScheduledTaskHistory(Base):
    """定时任务执行历史"""
    __tablename__ = 'scheduled_task_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheduled_task_id = Column(Integer, ForeignKey('scheduled_tasks.id'), nullable=False, index=True)
    batch_id = Column(String(36))  # 关联的批量注册 batch_id
    status = Column(String(20), default='running')  # running, completed, failed
    total = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    scheduled_task = relationship('ScheduledTask')