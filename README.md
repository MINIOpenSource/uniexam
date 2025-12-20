# Online Exam System (Refactored)

This is a production-ready, refactored version of the Online Exam System, built with **FastAPI**, **SQLAlchemy (Async)**, and **SQLite**.

## Features

*   **Robust Architecture**: Clean architecture with separation of concerns (API, Services, Database, Schemas).
*   **Security**:
    *   **Argon2** Password Hashing.
    *   **Opaque Tokens**: Secure, random tokens stored in the database (no JWT).
    *   **Rate Limiting**: Persistent, SQLite-backed rate limiting to prevent abuse.
    *   **Audit Logging**: Tracks critical actions (login, data modification) in the database.
*   **Database**: SQLite with async support (via `aiosqlite`) using SQLAlchemy 2.0.
*   **Grading**:
    *   Auto-grading for Single Choice, Multiple Choice, and Fill-in-the-Blank.
    *   Manual grading interface for Subjective/Essay questions.
*   **REST API**: Fully versioned RESTful API (`/api/v1`).

## Installation

1.  **Clone the repository**.
2.  **Create a virtual environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```
3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Start the server**:
    ```bash
    uvicorn app.main:app --reload
    ```
2.  **Access Documentation**:
    *   Swagger UI: `http://localhost:8000/docs`
    *   ReDoc: `http://localhost:8000/redoc`

## Initial Setup

*   The system automatically creates a default admin account on startup:
    *   **Username**: `admin`
    *   **Password**: `admin` (Change this immediately via API!)

## Testing

Run the test suite using `pytest`:

```bash
pytest
```
