# ၁။ Python ရဲ့ အပေါ့ပါးဆုံး image ကို အခြေခံအဖြစ် ယူမယ်
FROM python:3.10-slim

# ၂။ Container ထဲမှာ code တွေထားမယ့် နေရာကို သတ်မှတ်မယ်
WORKDIR /app

# ၃။ System ပိုင်းဆိုင်ရာ လိုအပ်တဲ့ tools အချို့ကို အရင်သွင်းမယ်
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# ၄။ သင့်ရဲ့ requirements ဖိုင်ကို container ထဲ ကူးထည့်မယ်
COPY requirements.txt .

# ၅။ လိုအပ်တဲ့ library တွေကို သွင်းမယ်
RUN pip install --no-cache-dir -r requirements.txt

# ၆။ သင့်ရဲ့ code တွေ (app.py, stellar_logic.py စသည်) အားလုံးကို container ထဲ ကူးထည့်မယ်
COPY . .

# ၇။ Streamlit က သုံးမယ့် Port 8501 ကို ဖွင့်ပေးမယ်
EXPOSE 8501

# ၈။ Container စတက်တာနဲ့ app ကို run မယ့် command
# --server.address=0.0.0.0 က cloud ပေါ်မှာ အပြင်ကနေ ဝင်ကြည့်လို့ရအောင် လုပ်ပေးတာပါ
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
