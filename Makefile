# Vỏ mỏng: mọi logic nằm trong scripts/task.sh để chạy được cả khi máy không có make
# (Windows + Git Bash: bash scripts/task.sh <lệnh>). Có GNU make (WSL/VM/GĐ2) thì: make <lệnh>.
.RECIPEPREFIX := >
SHELL := bash
TARGETS := setup dev run test lint fmt migrate seed backup sync-skill test-pg pg-temp replay create-admin restore e2e tls-check help
.PHONY: $(TARGETS)
.DEFAULT_GOAL := help

$(TARGETS):
> @bash scripts/task.sh $@
