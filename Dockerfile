FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
# RapidOCR depende de opencv-python, que exige libGL y no esta en la imagen
# slim. La variante headless expone el mismo modulo cv2 sin esa dependencia.
RUN pip install --no-cache-dir -r requirements.txt \
 && pip uninstall -y opencv-python \
 && pip install --no-cache-dir --force-reinstall opencv-python-headless \
 && python -c "import cv2, rapidocr_onnxruntime; print('cv2', cv2.__version__)"

# El vocabulario de Showdown se hornea en la imagen: en tiempo de ejecucion el
# contenedor no necesita salir a internet para validar nombres.
COPY scripts/ scripts/
RUN python scripts/build_dex.py

COPY app/ app/

ENV VISION_BACKEND=ocr \
    PYTHONUNBUFFERED=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health').read()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
