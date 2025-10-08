from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
from pdf_parser import parse_policy_pdf
from comparison import compare_policies

load_dotenv()

app = FastAPI(title="Insurance Policy Parser API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Insurance Policy Parser API", "status": "running"}

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

        return JSONResponse(content=policy_data)

    except Exception as e:
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

        return JSONResponse(content={
            "policy_a": policy_data_a,
            "policy_b": policy_data_b,
            "comparison": comparison
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error comparing policies: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
