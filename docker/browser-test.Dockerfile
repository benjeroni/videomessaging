FROM videomessaging-app
USER root
RUN pip install --no-cache-dir playwright==1.63.0 && playwright install-deps chromium
ENTRYPOINT ["python", "/work/tests/browser_smoke.py"]
