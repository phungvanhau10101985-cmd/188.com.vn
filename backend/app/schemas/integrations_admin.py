"""Admin — tổng quan trạng thái API key / bí mật tích hợp (không trả giá trị thật)."""

from pydantic import BaseModel, Field

from typing import List


class AdminIntegrationKeyRow(BaseModel):
    env_var: str = Field(..., description="Tên biến môi trường backend")
    label: str = Field(..., description="Nhãn hiển thị")
    configured: bool = Field(..., description="True nếu backend có giá trị khả dụng (độ dài tối thiểu)")
    hint: str = Field("", description="Gợi ý cấu hình")


class AdminIntegrationKeyGroup(BaseModel):
    title: str
    items: List[AdminIntegrationKeyRow]


class AdminIntegrationKeysOverviewOut(BaseModel):
    groups: List[AdminIntegrationKeyGroup]
    disclaimer: str = Field(
        ...,
        description="Không hiển thị hay trả về nội dung bí mật — chỉ trạng thái đã cấu hình hay chưa.",
    )
