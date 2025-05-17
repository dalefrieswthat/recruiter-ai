#!/bin/bash

# Start the FastAPI application with uvicorn
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 4 