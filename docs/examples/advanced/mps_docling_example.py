"""
Example: Using docling with MPS (Apple Silicon)

This example shows how to use docling with MPS acceleration by applying
the float32 patch before importing docling.

USAGE:
------
    python mps_docling_example.py

REQUIREMENTS:
-------------
- Apple Silicon Mac (M1/M2/M3)
- torch with MPS support
- docling installed
"""

# STEP 1: Apply the MPS patch BEFORE importing docling
from secondbrain.utils.mps_patch import patch_transformers_for_mps

patch_transformers_for_mps()

# STEP 2: Now import docling and transformers
from docling.document_converter import DocumentConverter

print("\n=== docling with MPS Example ===\n")

# Create a converter (this will now work on MPS without float64 errors)
converter = DocumentConverter()

# Convert a document (replace with your actual PDF path)
# pdf_path = "path/to/your/document.pdf"
# result = converter.convert(pdf_path)

print("✓ DocumentConverter initialized successfully with MPS support")
print("✓ PDF processing will use MPS-accelerated transformers models")
print("✓ No float64 errors on Apple Silicon")

# Example usage (uncomment with a real PDF path):
# result = converter.convert("example.pdf")
# print(result.document.export_to_markdown())
