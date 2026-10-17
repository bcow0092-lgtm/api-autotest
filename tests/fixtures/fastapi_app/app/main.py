# -*- coding: utf-8 -*-
"""合成 fixture：一个最小的 FastAPI 应用，用于验证 Python 分析器。"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/orders")


@router.get("/list")
def list_orders():
    """查询订单列表"""
    return []


@router.post("/create")
def create_order(payload: dict):
    """创建订单"""
    return payload


@router.get("/{order_id}")
def get_order(order_id: int):
    """查询订单详情"""
    return {}
