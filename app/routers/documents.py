"""
Documents Router - Driver document upload and verification
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
import os
import uuid
import shutil

from app.models.database import (
    get_db, Document, Driver, 
    DocumentType, DocumentStatus
)

router = APIRouter(prefix="/documents", tags=["Documents"])

# =============================================================================
# SCHEMAS
# =============================================================================

class DocumentResponse(BaseModel):
    """Response schema for a document"""
    document_id: str
    driver_id: str
    document_type: str
    status: str
    file_name: Optional[str] = None
    rejection_reason: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class DocumentsStatusResponse(BaseModel):
    """Response schema for all driver documents status"""
    driver_id: str
    verification_status: str  # complete, incomplete, pending
    documents_uploaded: int
    documents_required: int
    documents: List[DocumentResponse]


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document"""
    success: bool
    message: str
    document: Optional[DocumentResponse] = None


# =============================================================================
# CONFIG
# =============================================================================

# Required documents for verification
REQUIRED_DOCUMENTS = [
    DocumentType.PROFILE_PHOTO,
    DocumentType.NATIONAL_ID,
    DocumentType.DRIVERS_LICENSE,
    DocumentType.VEHICLE_REGISTRATION,
]

# Upload directory
UPLOAD_DIR = "uploads/documents"

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_verification_status(documents: List[Document]) -> str:
    """Calculate overall verification status"""
    if not documents:
        return "incomplete"
    
    required_types = set(REQUIRED_DOCUMENTS)
    uploaded_docs = {doc.document_type for doc in documents}
    
    # Check if all required docs are uploaded
    if not required_types.issubset(uploaded_docs):
        return "incomplete"
    
    # Check statuses
    statuses = [doc.status for doc in documents if doc.document_type in required_types]
    
    if all(s == DocumentStatus.APPROVED for s in statuses):
        return "verified"
    elif any(s == DocumentStatus.REJECTED for s in statuses):
        return "rejected"
    else:
        return "pending"


def generate_document_id() -> str:
    """Generate unique document ID"""
    return f"doc_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/driver/{driver_id}", response_model=DocumentsStatusResponse)
async def get_driver_documents(driver_id: str, db: Session = Depends(get_db)):
    """
    Get all documents status for a driver
    
    Why: App needs to show which documents are uploaded/pending/approved
    """
    # Verify driver exists
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Get existing documents
    existing_docs = db.query(Document).filter(Document.driver_id == driver_id).all()
    existing_types = {doc.document_type: doc for doc in existing_docs}
    
    # Build complete document list (including not uploaded)
    all_doc_types = list(DocumentType)
    documents = []
    
    for doc_type in all_doc_types:
        if doc_type in existing_types:
            doc = existing_types[doc_type]
            documents.append(DocumentResponse(
                document_id=doc.document_id,
                driver_id=doc.driver_id,
                document_type=doc.document_type.value,
                status=doc.status.value,
                file_name=doc.file_name,
                rejection_reason=doc.rejection_reason,
                uploaded_at=doc.uploaded_at,
                reviewed_at=doc.reviewed_at
            ))
        else:
            # Document not uploaded yet
            documents.append(DocumentResponse(
                document_id="",
                driver_id=driver_id,
                document_type=doc_type.value,
                status=DocumentStatus.NOT_UPLOADED.value,
                file_name=None,
                rejection_reason=None,
                uploaded_at=None,
                reviewed_at=None
            ))
    
    # Calculate status
    verification_status = get_verification_status(existing_docs)
    uploaded_count = len([d for d in documents if d.status != DocumentStatus.NOT_UPLOADED.value])
    
    return DocumentsStatusResponse(
        driver_id=driver_id,
        verification_status=verification_status,
        documents_uploaded=uploaded_count,
        documents_required=len(REQUIRED_DOCUMENTS),
        documents=documents
    )


@router.post("/driver/{driver_id}/upload", response_model=DocumentUploadResponse)
async def upload_document(
    driver_id: str,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload a document for a driver
    
    Why: Drivers need to upload ID, license, etc. for verification
    """
    # Verify driver exists
    driver = db.query(Driver).filter(Driver.driver_id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Validate document type
    try:
        doc_type = DocumentType(document_type)
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid document type. Valid types: {[t.value for t in DocumentType]}"
        )
    
    # Validate file type
    allowed_extensions = {".jpg", ".jpeg", ".png", ".pdf"}
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {allowed_extensions}"
        )
    
    # Create file path
    file_name = f"{driver_id}_{document_type}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    
    # Save file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # Get file size
    file_size = os.path.getsize(file_path)
    
    # Check if document already exists
    existing_doc = db.query(Document).filter(
        Document.driver_id == driver_id,
        Document.document_type == doc_type
    ).first()
    
    if existing_doc:
        # Update existing document
        existing_doc.file_path = file_path
        existing_doc.file_name = file_name
        existing_doc.file_size = file_size
        existing_doc.status = DocumentStatus.PENDING
        existing_doc.rejection_reason = None
        existing_doc.updated_at = datetime.utcnow()
        existing_doc.uploaded_at = datetime.utcnow()
        doc = existing_doc
    else:
        # Create new document
        doc = Document(
            document_id=generate_document_id(),
            driver_id=driver_id,
            document_type=doc_type,
            file_path=file_path,
            file_name=file_name,
            file_size=file_size,
            status=DocumentStatus.PENDING
        )
        db.add(doc)
    
    db.commit()
    db.refresh(doc)
    
    return DocumentUploadResponse(
        success=True,
        message=f"{document_type} uploaded successfully",
        document=DocumentResponse(
            document_id=doc.document_id,
            driver_id=doc.driver_id,
            document_type=doc.document_type.value,
            status=doc.status.value,
            file_name=doc.file_name,
            rejection_reason=doc.rejection_reason,
            uploaded_at=doc.uploaded_at,
            reviewed_at=doc.reviewed_at
        )
    )


@router.delete("/driver/{driver_id}/{document_type}")
async def delete_document(
    driver_id: str,
    document_type: str,
    db: Session = Depends(get_db)
):
    """
    Delete a document
    
    Why: Driver may want to replace a rejected document
    """
    try:
        doc_type = DocumentType(document_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document type")
    
    doc = db.query(Document).filter(
        Document.driver_id == driver_id,
        Document.document_type == doc_type
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete file if exists
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    
    # Delete record
    db.delete(doc)
    db.commit()
    
    return {"success": True, "message": f"{document_type} deleted"}


@router.get("/{document_id}/download")
async def download_document(document_id: str, db: Session = Depends(get_db)):
    """
    Download/view a document
    
    Why: Admin or driver may need to view uploaded document
    """
    from fastapi.responses import FileResponse
    
    doc = db.query(Document).filter(Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=doc.file_path,
        filename=doc.file_name,
        media_type="application/octet-stream"
    )