from flask import Flask, request, render_template, send_file, jsonify
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import os
import spacy
import PyPDF2
import io
from werkzeug.utils import secure_filename
from base64 import b64encode
import requests
from bs4 import BeautifulSoup

app = Flask(__name__, template_folder="templates")

# Load SpaCy's English NLP model
nlp = spacy.load("en_core_web_sm")

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(filepath):
    with open(filepath, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ''.join(page.extract_text() or '' for page in reader.pages)
    return text

def process_text_with_nlp(text):
    doc = nlp(text)
    return [(ent.text, ent.label_) for ent in doc.ents]

def create_pdf(name, experience, education, entities, preview=False):
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    content = []

    if preview:
        content.append(Paragraph("<b>PREVIEW</b>", styles["Title"]))
        content.append(Spacer(1, 12))

    content.append(Paragraph(f"<b>Name:</b> {name}", styles["Normal"]))
    content.append(Spacer(1, 12))
    content.append(Paragraph("<b>Experience:</b>", styles["Normal"]))
    content.append(Paragraph(experience, styles["Normal"]))
    content.append(Spacer(1, 12))
    content.append(Paragraph("<b>Education:</b>", styles["Normal"]))
    content.append(Paragraph(education, styles["Normal"]))
    content.append(Spacer(1, 12))
    content.append(Paragraph("<b>Projects:</b>", styles["Normal"]))
    for entity, label in entities:
        content.append(Paragraph(f"{entity} ({label})", styles["Normal"]))
    content.append(Spacer(1, 12))
    pdf.build(content)
    buffer.seek(0)
    return buffer

@app.route("/")
def index():
    if not os.path.exists(os.path.join("templates", "index.html")):
        return "Error: index.html not found in templates folder", 500
    return render_template("index.html"), 200, {'Content-Type': 'text/html'}

@app.route("/preview-resume", methods=["POST"])
def preview_resume():
    try:
        required_fields = ['name', 'experience', 'education']
        for field in required_fields:
            if not request.form.get(field):
                return jsonify({"error": f"{field} is required"}), 400
        
        name = request.form["name"]
        experience = request.form["experience"]
        education = request.form["education"]
        entities = []
        uploaded_files = []

        for file_type in ['projects', 'certificates']:
            if file_type in request.files:
                for file in request.files.getlist(file_type):
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        uploaded_files.append(filepath)
        
        extracted_text = ''.join(
            extract_text_from_pdf(filepath) if filepath.endswith('.pdf') 
            else open(filepath, 'r', encoding='utf-8').read() for filepath in uploaded_files
        )

        if extracted_text:
            entities = process_text_with_nlp(extracted_text)
        
        for filepath in uploaded_files:
            os.remove(filepath)
        
        pdf_buffer = create_pdf(name, experience, education, entities, preview=True)
        pdf_base64 = b64encode(pdf_buffer.read()).decode()
        
        return jsonify({
            "preview": pdf_base64,
            "success": True
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/scrape-jobs", methods=["GET"])
def scrape_jobs():
    try:
        job_url = "https://remoteok.io/"
        response = requests.get(job_url)
        soup = BeautifulSoup(response.text, "html.parser")

        jobs = []
        for job in soup.find_all("tr", class_="job"):
            title = job.find("h2")
            company = job.find("h3")
            skills = job.find_all("span", class_="tag")

            job_data = {
                "title": title.text.strip() if title else "N/A",
                "company": company.text.strip() if company else "N/A",
                "skills": [skill.text.strip() for skill in skills] if skills else [],
            }

            jobs.append(job_data)

        return jsonify({"jobs": jobs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/generate-roadmap", methods=["GET"])
def generate_roadmap():
    try:
        response = requests.get(request.url_root + "scrape-jobs")
        jobs = response.json().get("jobs", []) if response.status_code == 200 else []
        skill_counts = {}

        for job in jobs:
            for skill in job["skills"]:
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
        
        sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
        roadmap = [skill for skill, _ in sorted_skills[:10]]
        
        if not roadmap:
            roadmap_sh_url = "https://roadmap.sh/api/data/frontend"
            roadmap_response = requests.get(roadmap_sh_url)
            if roadmap_response.status_code == 200:
                roadmap = roadmap_response.json().get("stages", [])
                roadmap = [stage["title"] for stage in roadmap[:10]]
            else:
                roadmap = ["Learn Python", "Understand Data Structures", "Build Projects", "Master Databases", "Learn Web Development"]

        return jsonify({"roadmap": roadmap})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
