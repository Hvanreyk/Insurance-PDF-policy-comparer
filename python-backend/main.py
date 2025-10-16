from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import os
import gc
from dotenv import load_dotenv
from pdf_parser import parse_policy_pdf
from comparison import compare_policies
from routes.ucc import router as ucc_router

load_dotenv()

app = FastAPI(title="Insurance Policy Parser API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(ucc_router)

@app.get("/")
async def root():
    return {"message": "Insurance Policy Parser API", "status": "running"}

@app.head("/")
async def root_head():
    return Response(status_code=200)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "insurance-policy-parser"}

@app.head("/health")
async def health_head():
    return Response(status_code=200)

@app.post("/api/parse-policy")
async def parse_policy(file: UploadFile = File(...)):
    """
    Parse an insurance policy PDF and extract structured data
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        contents = await file.read()

        policy_data = parse_policy_pdf(contents)

        del contents
        gc.collect()

        return JSONResponse(content=policy_data)

    except Exception as e:
        gc.collect()
        raise HTTPException(status_code=500, detail=f"Error parsing PDF: {str(e)}")

@app.post("/api/compare-policies")
async def compare_policies_endpoint(
    policy_a: UploadFile = File(...),
    policy_b: UploadFile = File(...)
):
    """
    Compare two insurance policies
    """
    try:
        contents_a = await policy_a.read()
        contents_b = await policy_b.read()

        policy_data_a = parse_policy_pdf(contents_a)
        policy_data_b = parse_policy_pdf(contents_b)

        comparison = compare_policies(policy_data_a, policy_data_b)

        del contents_a, contents_b
        gc.collect()

        return JSONResponse(content={
            "policy_a": policy_data_a,
            "policy_b": policy_data_b,
            "comparison": comparison
        })

    except Exception as e:
        gc.collect()
        raise HTTPException(status_code=500, detail=f"Error comparing policies: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
