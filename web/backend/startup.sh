#!/bin/bash

# Startup script for the backend server

# Activate the root virtual environment
echo "Activating the root virtual environment..."
source ../../venv/bin/activate

# Start the backend server
echo "Starting the backend server..."
uvicorn main:app --reload --port 8000 