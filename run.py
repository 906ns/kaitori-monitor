#!/usr/bin/env python3
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

if __name__ == "__main__":
    import uvicorn
    # reload=Falseでサブプロセス問題を回避
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)