FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
# RapidOCR depends on opencv-python, which needs libGL and is not present in the
# slim image. The headless variant exposes the same cv2 module without it.
RUN pip install --no-cache-dir -r requirements.txt \
 && pip uninstall -y opencv-python \
 && pip install --no-cache-dir --force-reinstall opencv-python-headless \
 && python -c "import cv2, rapidocr_onnxruntime; print('cv2', cv2.__version__)"

# Showdown's vocabulary is baked into the image: at run time the container never
# needs to reach the internet to validate a name.
COPY scripts/ scripts/
RUN python scripts/build_dex.py

COPY app/ app/

ENV VISION_BACKEND=ocr \
    PYTHONUNBUFFERED=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health').read()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
