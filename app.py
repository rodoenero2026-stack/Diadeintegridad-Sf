import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dia_integridad_san_fernando_chiapas_secure_key')
csrf = CSRFProtect(app)

# Configuración de Cloudinary (si están presentes las variables de entorno)
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True
    )

@app.context_processor
def utility_processor():
    def get_file_url(url_path):
        if not url_path:
            return ''
        if url_path.startswith('http://') or url_path.startswith('https://'):
            return url_path
        return url_for('static', filename=url_path)
    return dict(get_file_url=get_file_url)

# Configuración de credenciales de Administrador (leídas desde variables de entorno)
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'IntegridadSF2026')

# Configuración de subida de archivos (almacenamiento local o Cloudinary)
UPLOAD_FOLDER = os.path.join('static', 'img')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
METADATA_FILE = os.path.join(UPLOAD_FOLDER, 'metadata.json')
BUZON_FILE = os.path.join(UPLOAD_FOLDER, 'buzon.json')

def is_cloudinary_enabled():
    return bool(
        os.environ.get('CLOUDINARY_URL') or 
        (os.environ.get('CLOUDINARY_CLOUD_NAME') and os.environ.get('CLOUDINARY_API_KEY') and os.environ.get('CLOUDINARY_API_SECRET'))
    )

def upload_file_to_storage(file, month, timestamp):
    ext = file.filename.rsplit('.', 1)[1].lower()
    safe_name = f"info_{month}_{timestamp}.{ext}"
    filename = secure_filename(safe_name)

    if is_cloudinary_enabled():
        try:
            resource_type = "raw" if ext == 'pdf' else "auto"
            upload_result = cloudinary.uploader.upload(
                file,
                folder="san_fernando_integridad",
                public_id=f"info_{month}_{timestamp}",
                resource_type=resource_type
            )
            file_url = upload_result.get('secure_url')
            public_id = upload_result.get('public_id')
            return filename, file_url, public_id
        except Exception as e:
            print(f"Error al subir a Cloudinary: {e}")

    # Respaldo en almacenamiento local
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)
    file_url = f"img/{filename}"
    return filename, file_url, None

def delete_file_from_storage(info):
    public_id = info.get('public_id')
    file_url = info.get('url', '')
    filename = info.get('filename', '')

    if is_cloudinary_enabled():
        try:
            if public_id:
                cloudinary.uploader.destroy(public_id)
            elif file_url.startswith('http'):
                parts = file_url.split('/')
                if 'san_fernando_integridad' in parts:
                    idx = parts.index('san_fernando_integridad')
                    pid = '/'.join(parts[idx:]).rsplit('.', 1)[0]
                    cloudinary.uploader.destroy(pid)
        except Exception as e:
            print(f"Error al eliminar de Cloudinary: {e}")

    if filename:
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception as e:
                print(f"Error al eliminar archivo local: {e}")


# Meses disponibles para el programa 2026
MONTHS = [
    {"id": "enero", "name": "Enero 2026"},
    {"id": "febrero", "name": "Febrero 2026"},
    {"id": "marzo", "name": "Marzo 2026"},
    {"id": "abril", "name": "Abril 2026"},
    {"id": "mayo", "name": "Mayo 2026"},
    {"id": "junio", "name": "Junio 2026"},
    {"id": "julio", "name": "Julio 2026"}
]

def load_metadata():
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_metadata(data):
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_buzon():
    if os.path.exists(BUZON_FILE):
        try:
            with open(BUZON_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_buzon(data):
    with open(BUZON_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Configuración opcional de correo electrónico (SMTP)
# Puede configurarse mediante variables de entorno
SMTP_SERVER = os.environ.get('SMTP_SERVER', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
ADMIN_EMAIL_RECIPIENT = os.environ.get('ADMIN_EMAIL_RECIPIENT', '')

def enviar_notificacion_correo(msg_data):
    """Envía notificación por correo si las credenciales SMTP están configuradas."""
    if not SMTP_SERVER or not SMTP_USER or not SMTP_PASSWORD or not ADMIN_EMAIL_RECIPIENT:
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        subject = f"[Buzón Integridad San Fernando] Nuevo Reporte: {msg_data.get('asunto')}"
        body = f"""Se ha recibido una nueva solicitud en el Buzón de Integridad municipal:

Nombre: {msg_data.get('nombre')}
Correo: {msg_data.get('email')}
Tipo de Solicitud: {msg_data.get('asunto')}
Fecha: {msg_data.get('date_submitted')}

Mensaje:
----------------------------------------
{msg_data.get('mensaje')}
----------------------------------------
"""
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = ADMIN_EMAIL_RECIPIENT
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error al enviar correo de notificación: {e}")
        return False

# --- RUTAS PÚBLICAS ---

@app.route('/')
def inicio():
    return render_template('inicio.html', active_page='inicio')

@app.route('/actividades')
def actividades():
    infografias = load_metadata()
    # Organizar infografías por mes
    gallery = {m['id']: [] for m in MONTHS}
    for info in infografias:
        month_id = info.get('month')
        if month_id in gallery:
            gallery[month_id].append(info)
            
    return render_template('actividades.html', 
                           active_page='actividades', 
                           months=MONTHS, 
                           gallery=gallery)

@app.route('/contacto', methods=['GET', 'POST'])
def contacto():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        asunto = request.form.get('asunto')
        mensaje = request.form.get('mensaje')
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        new_msg = {
            'id': f"msg_{timestamp}",
            'nombre': nombre,
            'email': email,
            'asunto': asunto,
            'mensaje': mensaje,
            'date_submitted': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'leido': False
        }
        
        mensajes = load_buzon()
        mensajes.insert(0, new_msg)
        save_buzon(mensajes)
        
        # Intentar enviar notificación por correo si SMTP está configurado
        enviar_notificacion_correo(new_msg)
        
        flash(f'¡Gracias {nombre}! Tu reporte sobre "{asunto}" ha sido enviado correctamente al Buzón de Integridad municipal de San Fernando.', 'success')
        return redirect(url_for('contacto'))
        
    return render_template('contacto.html', active_page='contacto')

# --- RUTAS DE AUTENTICACIÓN ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('admin_panel'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username
            flash('Has iniciado sesión correctamente como Administrador.', 'success')
            return redirect(url_for('admin_panel'))
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')
            
    return render_template('login.html', active_page='login')

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente.', 'success')
    return redirect(url_for('inicio'))

# --- PANEL PRIVADO DE ADMINISTRADOR ---

def login_required(f):
    import functools
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Por favor inicia sesión para acceder a esta sección.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin')
@login_required
def admin_panel():
    infografias = load_metadata()
    mensajes = load_buzon()
    unread_count = sum(1 for m in mensajes if not m.get('leido'))
    return render_template('admin.html', 
                           active_page='admin', 
                           months=MONTHS, 
                           infografias=infografias,
                           mensajes=mensajes,
                           unread_count=unread_count)

@app.route('/admin/subir', methods=['POST'])
@login_required
def subir_infografia():
    month = request.form.get('month')
    title = request.form.get('title', 'Sin título')
    description = request.form.get('description', '')
    
    if not month or month not in [m['id'] for m in MONTHS]:
        flash('Selecciona un mes válido.', 'danger')
        return redirect(url_for('admin_panel'))
        
    if 'file' not in request.files:
        flash('Por favor selecciona un archivo.', 'danger')
        return redirect(url_for('admin_panel'))
        
    file = request.files['file']
    if file.filename == '':
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('admin_panel'))
        
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename, file_url, public_id = upload_file_to_storage(file, month, timestamp)
        
        new_entry = {
            'id': f"{month}_{timestamp}",
            'month': month,
            'title': title,
            'description': description,
            'filename': filename,
            'url': file_url,
            'public_id': public_id,
            'is_pdf': ext == 'pdf',
            'date_uploaded': datetime.now().strftime('%d/%m/%Y %H:%M')
        }
        
        data = load_metadata()
        data.append(new_entry)
        save_metadata(data)
        
        flash(f'Infografía "{title}" subida y registrada exitosamente.', 'success')
    else:
        flash('Tipo de archivo no permitido.', 'danger')
        
    return redirect(url_for('admin_panel'))

@app.route('/admin/editar/<info_id>', methods=['POST'])
@login_required
def editar_infografia(info_id):
    data = load_metadata()
    found = False
    
    month = request.form.get('month')
    title = request.form.get('title', 'Sin título')
    description = request.form.get('description', '')
    
    if not month or month not in [m['id'] for m in MONTHS]:
        flash('Selecciona un mes válido.', 'danger')
        return redirect(url_for('admin_panel'))
        
    for info in data:
        if info['id'] == info_id:
            info['title'] = title
            info['description'] = description
            info['month'] = month
            
            # Verificar si se subió un nuevo archivo para reemplazar el anterior
            if 'file' in request.files:
                file = request.files['file']
                if file and file.filename != '' and allowed_file(file.filename):
                    # Eliminar archivo viejo de almacenamiento
                    delete_file_from_storage(info)
                    
                    # Guardar nuevo archivo
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename, file_url, public_id = upload_file_to_storage(file, month, timestamp)
                    
                    info['filename'] = filename
                    info['url'] = file_url
                    info['public_id'] = public_id
                    info['is_pdf'] = ext == 'pdf'
            
            found = True
            break
            
    if found:
        save_metadata(data)
        flash(f'Infografía "{title}" editada correctamente.', 'success')
    else:
        flash('No se encontró la infografía especificada.', 'danger')
        
    return redirect(url_for('admin_panel'))

@app.route('/admin/eliminar/<info_id>', methods=['POST'])
@login_required
def eliminar_infografia(info_id):
    data = load_metadata()
    updated_data = []
    found = False
    
    for info in data:
        if info['id'] == info_id:
            delete_file_from_storage(info)
            found = True
        else:
            updated_data.append(info)
            
    if found:
        save_metadata(updated_data)
        flash('Infografía eliminada correctamente.', 'success')
    else:
        flash('No se encontró la infografía a eliminar.', 'danger')
        
    return redirect(url_for('admin_panel'))

# --- RUTAS DE GESTIÓN DEL BUZÓN ---

@app.route('/admin/mensaje/marcar_leido/<msg_id>', methods=['POST'])
@login_required
def marcar_leido_mensaje(msg_id):
    mensajes = load_buzon()
    for msg in mensajes:
        if msg['id'] == msg_id:
            msg['leido'] = not msg.get('leido', False) # alternar estado leído/no leído
            break
    save_buzon(mensajes)
    flash('Estado del mensaje actualizado.', 'success')
    return redirect(url_for('admin_panel') + '#buzon-tab-pane')

@app.route('/admin/mensaje/eliminar/<msg_id>', methods=['POST'])
@login_required
def eliminar_mensaje(msg_id):
    mensajes = load_buzon()
    updated_mensajes = [m for m in mensajes if m['id'] != msg_id]
    if len(updated_mensajes) < len(mensajes):
        save_buzon(updated_mensajes)
        flash('Mensaje eliminado permanentemente del buzón.', 'success')
    else:
        flash('No se encontró el mensaje a eliminar.', 'danger')
    return redirect(url_for('admin_panel') + '#buzon-tab-pane')

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')
    app.run(debug=debug_mode)

