-- ==================================================
-- MIGRATION: Thêm cột updated_at vào bảng categories
-- Version: 1.0
-- Created: 2026-01-28
-- Author: System Migration
-- Status: READY
-- ==================================================

-- SQLite không hỗ trợ ADD COLUMN với DEFAULT cho TIMESTAMP
-- Sẽ thêm cột và cập nhật giá trị sau