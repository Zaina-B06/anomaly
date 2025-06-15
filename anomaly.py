import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import hashlib
import re
from io import BytesIO
import pdfplumber
import pytesseract
from PIL import Image
import fitz  # PyMuPDF

# Set page config
st.set_page_config(page_title="Financial Document Anomaly Detector", layout="wide")

# Title and description
st.title("📄 Financial Document Anomaly Detector")
st.markdown("""
Upload your financial documents (bills, invoices) and we'll automatically detect:
- Duplicate documents
- Incorrect GST/TDS rates
- Missing GSTINs
- Calculation errors
- Other anomalies
""")

# GST rate mapping (as of knowledge cutoff in 2023)
GST_RATES = {
    '0': 0.0,
    '5': 5.0,
    '12': 12.0,
    '18': 18.0,
    '28': 28.0
}

# Sample TDS rates (simplified)
TDS_RATES = {
    'Salary': 10.0,
    'Contractor': 1.0,
    'Professional Fees': 10.0,
    'Rent': 10.0
}

# Initialize session state for stored documents
if 'processed_documents' not in st.session_state:
    st.session_state.processed_documents = []

# Helper functions
def extract_text_from_pdf(uploaded_file):
    """Extract text from PDF file"""
    text = ""
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
    except:
        st.warning("Could not extract text with pdfplumber, trying OCR")
        try:
            # Convert PDF to images and use OCR
            doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
            for page in doc:
                pix = page.get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text += pytesseract.image_to_string(img)
        except Exception as e:
            st.error(f"Failed to extract text: {str(e)}")
    return text

def extract_text_from_image(uploaded_file):
    """Extract text from image using OCR"""
    try:
        image = Image.open(uploaded_file)
        return pytesseract.image_to_string(image)
    except Exception as e:
        st.error(f"Failed to extract text from image: {str(e)}")
        return ""

def calculate_hash(content):
    """Calculate hash of document content for duplicate detection"""
    return hashlib.md5(content.encode()).hexdigest()

def extract_gstin(text):
    """Extract GSTIN from text using regex"""
    gstin_regex = r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1}'
    matches = re.findall(gstin_regex, text.upper())
    return matches[0] if matches else None

def extract_gst_rate(text):
    """Extract GST rate from text"""
    rate_regex = r'GST\s*@?\s*(\d+)%'
    matches = re.search(rate_regex, text, re.IGNORECASE)
    if matches:
        return matches.group(1)
    return None

def check_calculations(text):
    """Check for calculation anomalies"""
    # This is a simplified version - in reality you'd parse the amounts properly
    amount_regex = r'Total\s*:\s*(\d+\.\d{2})'
    matches = re.search(amount_regex, text, re.IGNORECASE)
    if not matches:
        return False, "Total amount not found"
    
    total = float(matches.group(1))
    
    # Check if subtotal + tax matches total (simplified)
    subtotal_regex = r'Sub\s*Total\s*:\s*(\d+\.\d{2})'
    subtotal_match = re.search(subtotal_regex, text, re.IGNORECASE)
    
    tax_regex = r'GST\s*:\s*(\d+\.\d{2})'
    tax_match = re.search(tax_regex, text, re.IGNORECASE)
    
    if subtotal_match and tax_match:
        subtotal = float(subtotal_match.group(1))
        tax = float(tax_match.group(1))
        calculated_total = subtotal + tax
        if not np.isclose(total, calculated_total, atol=0.01):
            return False, f"Calculation mismatch: {subtotal} + {tax} ≠ {total}"
    
    return True, "Calculations OK"

def validate_gst_rate(rate):
    """Validate if GST rate is standard"""
    if rate not in GST_RATES:
        return False, f"Non-standard GST rate: {rate}%"
    return True, f"Valid GST rate: {rate}%"

def process_document(uploaded_file, file_type):
    """Process uploaded document and detect anomalies"""
    anomalies = []
    
    # Read file content
    if file_type == "pdf":
        text = extract_text_from_pdf(uploaded_file)
    else:  # image
        text = extract_text_from_image(uploaded_file)
    
    if not text:
        anomalies.append(("Critical", "Could not extract text from document"))
        return anomalies, text
    
    # Check for duplicate document
    doc_hash = calculate_hash(text)
    if any(doc['hash'] == doc_hash for doc in st.session_state.processed_documents):
        anomalies.append(("High", "Duplicate document detected"))
    
    # GSTIN validation
    gstin = extract_gstin(text)
    if not gstin:
        anomalies.append(("High", "GSTIN not found in document"))
    else:
        # Basic GSTIN format validation
        if len(gstin) != 15:
            anomalies.append(("High", f"Invalid GSTIN format: {gstin}"))
    
    # GST rate validation
    gst_rate = extract_gst_rate(text)
    if gst_rate:
        is_valid, msg = validate_gst_rate(gst_rate)
        if not is_valid:
            anomalies.append(("Medium", msg))
    else:
        anomalies.append(("Low", "GST rate not specified"))
    
    # Calculation validation
    calc_ok, calc_msg = check_calculations(text)
    if not calc_ok:
        anomalies.append(("High", calc_msg))
    
    return anomalies, text

# File upload section
st.sidebar.header("Upload Documents")
uploaded_files = st.sidebar.file_uploader(
    "Upload financial documents (PDF or images)",
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=True
)

# Process button
if st.sidebar.button("Process Documents") and uploaded_files:
    progress_bar = st.progress(0)
    total_files = len(uploaded_files)
    
    for i, uploaded_file in enumerate(uploaded_files):
        # Determine file type
        file_type = uploaded_file.type.split('/')[-1]
        if file_type == 'pdf':
            file_type = "pdf"
        else:
            file_type = "image"
        
        # Process document
        st.write(f"Processing {uploaded_file.name}...")
        anomalies, text = process_document(uploaded_file, file_type)
        
        # Store document in session state
        doc_hash = calculate_hash(text)
        st.session_state.processed_documents.append({
            'name': uploaded_file.name,
            'hash': doc_hash,
            'text': text,
            'anomalies': anomalies,
            'timestamp': datetime.now()
        })
        
        # Update progress
        progress_bar.progress((i + 1) / total_files)
    
    st.success(f"Processed {total_files} documents!")

# Display results
if st.session_state.processed_documents:
    st.header("Detection Results")
    
    # Summary statistics
    total_docs = len(st.session_state.processed_documents)
    total_anomalies = sum(len(doc['anomalies']) for doc in st.session_state.processed_documents)
    critical_anomalies = sum(1 for doc in st.session_state.processed_documents 
                            for anomaly in doc['anomalies'] if anomaly[0] == "Critical")
    high_anomalies = sum(1 for doc in st.session_state.processed_documents 
                        for anomaly in doc['anomalies'] if anomaly[0] == "High")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Documents", total_docs)
    col2.metric("Total Anomalies", total_anomalies)
    col3.metric("Critical Anomalies", critical_anomalies)
    col4.metric("High Priority Anomalies", high_anomalies)
    
    # Detailed results
    st.subheader("Document Details")
    for doc in st.session_state.processed_documents:
        with st.expander(f"📄 {doc['name']} - {len(doc['anomalies'])} anomalies"):
            if doc['anomalies']:
                for severity, anomaly in doc['anomalies']:
                    if severity == "Critical":
                        st.error(f"🚨 {severity}: {anomaly}")
                    elif severity == "High":
                        st.warning(f"⚠️ {severity}: {anomaly}")
                    else:
                        st.info(f"ℹ️ {severity}: {anomaly}")
            else:
                st.success("✅ No anomalies detected")
            
            # Show document text (truncated)
            st.subheader("Extracted Text")
            st.text(doc['text'][:1000] + ("..." if len(doc['text']) > 1000 else ""))

# Clear data button
if st.sidebar.button("Clear All Data"):
    st.session_state.processed_documents = []
    st.rerun()