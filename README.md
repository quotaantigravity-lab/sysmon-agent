# SysMon Agent — 24/7 System Monitoring & Operations Assistant

AI Agent giám sát hệ thống 24/7, tự động hóa quy trình vận hành trực ca — từ phát hiện sự cố, phân tích alert đến tạo báo cáo bàn giao ca.

**Track:** Automation & Integration | **Claw-a-thon 2026**

---

## Bài toán & Giải pháp

### Vấn đề
- Kỹ sư trực ca phải theo dõi liên tục nhiều nguồn cảnh báo (Nagios, email, dashboard) → dễ bỏ sót.
- Khi có sự cố, soạn email thông báo thủ công → chậm, không nhất quán.
- Tra cứu SOP (quy trình vận hành tiêu chuẩn) từ tài liệu rời rạc → mất thời gian.
- Bàn giao ca thiếu cấu trúc → thông tin rơi rụng giữa các ca trực.

### Giải pháp
SysMon Agent là **một trợ lý AI duy nhất** cho toàn bộ ca trực:

| Chức năng | Mô tả |
|-----------|-------|
| 📊 **Dashboard tổng quan** | Metric cards hiển thị Critical/Warning/OK, sự cố mở, host bị ảnh hưởng — cập nhật real-time qua WebSocket |
| 🚨 **Cảnh báo Nagios** | Tự động đồng bộ alert từ email (IMAP), hiển thị theo mức độ, lọc theo trạng thái |
| ⚡ **Phát hiện leo thang** | Tự động phát hiện host có alert tăng dần mức độ nghiêm trọng trong time window configurable |
| 📋 **Quản lý log ca trực** | CRUD sự cố, bảo trì, ghi chú — phân loại theo loại/mức độ/trạng thái |
| 📚 **RAG trên SOP** | Tải lên tài liệu SOP (.docx, .xlsx, .pdf, .txt), AI tự động tra cứu khi được hỏi |
| 💬 **AI Chatbot** | Chat với AI để hỏi cách xử lý sự cố, soạn email incident, phân tích alert spike |
| 📧 **Soạn email incident** | Tự động trích xuất thông tin từ log → sinh email cảnh báo chuẩn mẫu |
| 📝 **Báo cáo bàn giao** | Tự động tổng hợp log ca trực thành báo cáo Markdown chuyên nghiệp |
| 🌙 **Dark/Light theme** | Chuyển đổi theme linh hoạt, lưu trạng thái bằng localStorage |

### Giá trị mang lại
- **Giảm 70% thời gian** soạn email incident & báo cáo bàn giao.
- **Phát hiện sớm** alert leo thang trước khi trở thành sự cố nghiêm trọng.
- **Không bỏ sót** thông tin giữa các ca trực nhờ log có cấu trúc.
- **Tra cứu SOP tức thì** thay vì tìm kiếm thủ công trong tài liệu.

---

## Kiến trúc & Công nghệ

```
┌─────────────────────────────────────────────────┐
│                   Frontend                       │
│  HTML5 + CSS3 (Glassmorphism) + Vanilla JS       │
│  WebSocket ← real-time updates                   │
└──────────────────┬──────────────────────────────┘
                   │ REST API + WebSocket
┌──────────────────▼──────────────────────────────┐
│              FastAPI Backend (Python 3.11)        │
│                                                   │
│  ┌─────────┐ ┌──────────┐ ┌─────────────────┐   │
│  │Log CRUD │ │ SOP RAG  │ │ Nagios IMAP     │   │
│  │(JSON DB)│ │(TF-IDF)  │ │ Alert Parser    │   │
│  └─────────┘ └──────────┘ └─────────────────┘   │
│  ┌─────────────┐ ┌──────────────────────────┐   │
│  │ Escalation  │ │ GreenNode MaaS (Chat)    │   │
│  │ Detection   │ │ minimax/minimax-m2.5     │   │
│  └─────────────┘ └──────────────────────────┘   │
│  ┌─────────────────────────────────────────┐    │
│  │        WebSocket Manager                │    │
│  │   (broadcast log/alert changes)         │    │
│  └─────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
```

**Tech Stack:**
- **Backend:** Python 3.11, FastAPI, Uvicorn
- **Frontend:** HTML5, CSS3 (Glassmorphism), Vanilla JavaScript
- **AI Model:** GreenNode MaaS — `minimax/minimax-m2.5`
- **Document Parsing:** pypdf, python-docx, openpyxl
- **Real-time:** WebSocket (FastAPI native)
- **Storage:** JSON file-based (zero external DB dependency)

---

## Cải tiến so với phiên bản gốc

| Tiêu chí | Bản gốc | Bản cải tiến |
|-----------|---------|---------------|
| Real-time | Polling | WebSocket broadcast |
| Dashboard | Không có | Metric cards + escalation panel |
| RAG | Keyword matching đơn giản | TF-IDF weighted scoring |
| Alert analysis | Basic list | Escalation detection với time window |
| UI | Glassmorphism cơ bản | Animated indicators, toast notifications, responsive |
| Theme | Dark only | Dark/Light toggle với CSS variables |
| Filters | Không có | Multi-filter (type, severity, status) |
| Architecture | Monolithic | Clean separation: API routes, WS manager, parsers |

---

## Hướng dẫn chạy

### Local
```bash
pip install -r requirements.txt
python app.py
# → http://127.0.0.1:8000
```

### Docker
```bash
docker build -t sysmon-agent:latest .
docker run -d -p 8000:8000 --name sysmon-agent sysmon-agent:latest
```

### Cấu hình API Key
1. Mở ứng dụng → bấm ⚙️ (Settings)
2. Nhập GreenNode API Key
3. (Tùy chọn) Cấu hình IMAP để đồng bộ alert Nagios từ email

### Triển khai lên AgentBase
```bash
git clone https://github.com/vngcloud/greennode-agentbase-skills.git
# Sử dụng /agentbase-wizard hoặc /agentbase-deploy
```

---

## Sử dụng

1. **Xem Dashboard:** Mở tab Dashboard để xem tổng quan hệ thống
2. **Thêm log:** Tab Log Ca Trực → "+ Thêm Log" → điền thông tin sự cố
3. **Chat với AI:** Tab AI Chat → hỏi về cách xử lý sự cố, yêu cầu soạn email
4. **Tải SOP:** Tab SOP Docs → "Tải lên" → chọn file .docx/.xlsx/.pdf/.txt
5. **Xem cảnh báo:** Tab Cảnh Báo → lọc theo mức độ
6. **Tạo báo cáo:** Tab Báo Cáo → nhập tên người bàn giao/nhận → "Tạo Báo Cáo"

---

**Team:** Võ Anh Duy | **Track:** Automation & Integration | **Claw-a-thon 2026**
