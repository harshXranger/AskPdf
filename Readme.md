# 📄 AskPDF – AI Powered PDF Reader & Chatbot

🚀 AskPDF is an intelligent PDF reader that allows users to **upload PDFs, ask questions, and get AI-powered answers with sources**.

It uses **Retrieval-Augmented Generation (RAG)** to provide accurate answers directly from your document.

---

## ✨ Features

* 📤 Upload PDF files
* 📖 View full PDF inside the app
* 💬 Chat with your PDF (like ChatGPT)
* ⚡ Real-time streaming responses (typing effect)
* 📌 Source tracking with page numbers
* 🔍 Click source → jump to PDF page
* 🧠 Semantic search using embeddings
* 🎯 Accurate answers using context from PDF

---

## 🛠️ Tech Stack

### Frontend

* React.js
* PDF.js (pdfjs-dist)

### Backend

* Flask
* FAISS (Vector Database)
* Sentence Transformers

### AI / LLM

* Ollama
* LLaMA 3.2 (local model)

---

## ⚙️ How It Works

```text
Upload PDF
     ↓
Extract Text (PyMuPDF)
     ↓
Chunk Text
     ↓
Generate Embeddings
     ↓
Store in FAISS
     ↓
Ask Question
     ↓
Retrieve Relevant Chunks
     ↓
Generate Answer (LLM)
     ↓
Show Answer + Source Pages
```

---

## 📂 Project Structure

```text
AskPDF/
│
├── backend/
│   ├── app.py
│   ├── uploads/
│   └── vector_stores/
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatUI.jsx
│   │   │   ├── PDFViewer.jsx
│   │   │   └── PDFUploader.jsx
│   │   └── App.jsx
│
└── README.md
```

---

## 🚀 Installation & Setup

### 1️⃣ Clone the repository

```bash
git clone https://github.com/your-username/AskPDF.git
cd AskPDF
```

---

### 2️⃣ Backend Setup

```bash
cd backend

pip install -r requirements.txt

python app.py
```

Server runs at:

```
http://127.0.0.1:5000
```

---

### 3️⃣ Install & Run Ollama

```bash
ollama run llama3.2:1b
```

---

### 4️⃣ Frontend Setup

```bash
cd frontend

npm install

npm run dev
```

Frontend runs at:

```
http://localhost:5173
```

---

## 📸 Screenshots (Add your images here)

* Upload PDF UI
  <img width="1065" height="667" alt="image" src="https://github.com/user-attachments/assets/10de3a2d-62d1-4f57-b46b-c97b76e553bb" />

* Chat Interface
* <img width="573" height="551" alt="image" src="https://github.com/user-attachments/assets/1d76d53b-a3ff-47ee-b623-f9ab85ac264f" />

* Source Navigation
<img width="1067" height="849" alt="image" src="https://github.com/user-attachments/assets/614fa63b-dbbf-47e7-a8b3-4f05cfdd05fb" />

---

## 🎯 Example Usage

```text
Q: What is Machine Learning?

A: Machine learning is a subset of AI...

Source:
Page 1-5
```

---

## 🔥 Future Improvements

* 📌 Highlight exact text inside PDF
* 📚 Multi-PDF support
* 🧾 Chat history with database
* 🔐 Authentication (Login/Signup)
* 🌙 Dark mode UI

---

## 👨‍💻 Author

Harsh Singh
B.Tech IT Student

---

⭐ If you like this project, give it a star on GitHub!
