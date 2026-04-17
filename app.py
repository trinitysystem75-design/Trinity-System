import os
import random
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
from sqlalchemy import func
from flask_mail import Mail, Message

app = Flask(__name__)

# --- CONFIGURACIÓN ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
app.config['SECRET_KEY'] = 'trinity_gold_final_2026'
app.config['UPLOAD_FOLDER'] = 'static/comprobantes'
DOMINIO_OFICIAL = "https://www.trinity-system75.com"

# --- EMAIL SMTP ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'trinitysystem75@gmail.com'
app.config['MAIL_PASSWORD'] = 'liqmcabffpksndfg' 
mail = Mail(app)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- MODELOS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    codigo_verificacion = db.Column(db.String(6), nullable=True) 
    esta_verificado = db.Column(db.Boolean, default=False)
    referred_by = db.Column(db.Integer, nullable=True) 
    balance = db.Column(db.Float, default=0.0)      
    roi_total = db.Column(db.Float, default=0.0)    
    deposito_status = db.Column(db.String(20), default='INACTIVO')
    transacciones = db.relationship('Transaccion', backref='dueno', lazy=True)

class Transaccion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20))
    monto = db.Column(db.Float)    
    fee = db.Column(db.Float, default=0.0) 
    comprobante = db.Column(db.String(200), nullable=True)
    fecha = db.Column(db.String(20), default=datetime.now().strftime('%Y-%m-%d'))
    estado = db.Column(db.String(20), default='PENDIENTE')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# --- GARANTÍA DE TABLAS ---
with app.app_context():
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    if user and user.deposito_status == 'BANEADO': return None
    return user

# --- RUTAS ---
@app.route('/')
def home(): return redirect(url_for('login'))

@app.route('/login')
def login(): return render_template('login.html')

@app.route('/registro')
def registro():
    ref_id = request.args.get('ref')
    return render_template('registro.html', ref_id=ref_id)

@app.route('/crear_usuario', methods=['POST'])
def crear_usuario():
    u = request.form.get('username')
    e = request.form.get('email')
    p = request.form.get('password')
    ref = request.args.get('ref')
    clean_ref = int(ref) if ref and ref.isdigit() else None
    
    # Validación de duplicados
    if User.query.filter_by(username=u).first():
        flash("¡Error! Ese nombre de usuario ya está registrado.")
        return redirect(url_for('registro'))
    if User.query.filter_by(email=e).first():
        flash("¡Error! Este correo electrónico ya tiene cuenta.")
        return redirect(url_for('registro'))

    codigo = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    try:
        msg = Message("Código de Verificación", sender="trinitysystem75@gmail.com", recipients=[e])
        msg.body = f"Tu código es: {codigo}"
        mail.send(msg)
    except Exception as err:
        print(f"DEBUG ERROR: {err}")
    
    nuevo = User(username=u, email=e, password=p, referred_by=clean_ref, codigo_verificacion=codigo, esta_verificado=False)
    db.session.add(nuevo)
    db.session.commit()
    return redirect(url_for('verificar_cuenta', username=u))

@app.route('/verificar_cuenta/<username>')
def verificar_cuenta(username): return render_template('verificar.html', username=username)

@app.route('/validar_codigo', methods=['POST'])
def validar_codigo():
    u, codigo_ingresado = request.form.get('username'), request.form.get('codigo')
    user = User.query.filter_by(username=u).first()
    if user and user.codigo_verificacion == codigo_ingresado:
        user.esta_verificado = True
        db.session.commit()
        return redirect(url_for('login'))
    flash("Código incorrecto.")
    return redirect(url_for('verificar_cuenta', username=u))

@app.route('/entrar', methods=['POST'])
def entrar():
    u, p = request.form.get('username'), request.form.get('password')
    user = User.query.filter_by(username=u, password=p).first()
    if user:
        if user.deposito_status == 'BANEADO':
            flash("Cuenta suspendida.")
            return redirect(url_for('login'))
        if not user.esta_verificado:
            flash("Verifica tu cuenta primero.")
            return redirect(url_for('verificar_cuenta', username=u))
        login_user(user)
        return redirect(url_for('dashboard'))
    flash("Error: Credenciales incorrectas.")
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    conteo_red = User.query.filter_by(referred_by=current_user.id).count()
    ganancia_hoy = current_user.balance * 0.012 
    roi_porcentaje = (current_user.roi_total / current_user.balance * 100) if current_user.balance > 0 else 0
    link_ref = f"{DOMINIO_OFICIAL}/registro?ref={current_user.id}"
    historial = Transaccion.query.filter_by(user_id=current_user.id).order_by(Transaccion.id.desc()).limit(5).all()
    return render_template('dashboard.html', link_ref=link_ref, conteo_red=conteo_red, ganancia_hoy=ganancia_hoy, roi_porcentaje=roi_porcentaje, historial=historial)

@app.route('/mi_red')
@login_required
def mi_red():
    link_ref = f"{DOMINIO_OFICIAL}/registro?ref={current_user.id}"
    referidos = User.query.filter_by(referred_by=current_user.id).all()
    return render_template('red.html', link_ref=link_ref, referidos=referidos)

@app.route('/depositar')
@login_required
def depositar():
    link_ref = f"{DOMINIO_OFICIAL}/registro?ref={current_user.id}"
    return render_template('depositar.html', link_ref=link_ref)

@app.route('/retirar')
@login_required
def retirar():
    link_ref = f"{DOMINIO_OFICIAL}/registro?ref={current_user.id}"
    return render_template('retirar.html', link_ref=link_ref)

@app.route('/subir_pago', methods=['POST'])
@login_required
def subir_pago():
    try:
        monto = float(request.form.get('monto_enviado', 0))
        if monto < 30:
            flash("Mínimo $30 USD.")
            return redirect(url_for('depositar'))
        if 'comprobante' in request.files:
            file = request.files['comprobante']
            if file and file.filename != '':
                ext = file.filename.split('.')[-1]
                fn = f"dep_{current_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                current_user.deposito_status = 'PENDIENTE'
                db.session.add(Transaccion(tipo='DEPÓSITO', monto=monto, comprobante=fn, user_id=current_user.id))
                db.session.commit()
                flash("Pago enviado.")
    except: flash("Error en el monto.")
    return redirect(url_for('dashboard'))

@app.route('/system-root-portal')
@login_required
def admin_panel():
    if current_user.username != 'Cristhian2704': return redirect(url_for('dashboard'))
    usuarios = User.query.all()
    pagos = Transaccion.query.filter_by(estado='PENDIENTE', tipo='DEPÓSITO').all()
    retiros = Transaccion.query.filter_by(estado='PENDIENTE', tipo='RETIRO').all()
    cap_total = db.session.query(func.sum(User.balance)).scalar() or 0.0
    roi_pagar = db.session.query(func.sum(User.roi_total)).scalar() or 0.0
    return render_template('admin_trinity.html', usuarios=usuarios, pagos=pagos, retiros=retiros, capital_total=cap_total, roi_por_pagar=roi_pagar)

@app.route('/aprobar_pago/<int:tx_id>', methods=['POST'])
@login_required
def aprobar_pago(tx_id):
    if current_user.username != 'Cristhian2704': return redirect(url_for('dashboard'))
    tx = Transaccion.query.get(tx_id)
    if tx and tx.estado == 'PENDIENTE':
        u = User.query.get(tx.user_id)
        u.balance += tx.monto
        u.deposito_status = 'ACTIVO'
        tx.estado = 'APROBADO'
        if u.referred_by:
            patro = User.query.get(u.referred_by)
            if patro:
                bono = tx.monto * 0.10
                patro.roi_total += bono
                db.session.add(Transaccion(tipo='BONO_RED', monto=bono, estado='APROBADO', user_id=patro.id))
        db.session.commit()
        flash("Depósito aprobado.")
    return redirect(url_for('admin_panel'))

@app.route('/aprobar_retiro/<int:tx_id>', methods=['POST'])
@login_required
def aprobar_retiro(tx_id):
    if current_user.username != 'Cristhian2704': return redirect(url_for('dashboard'))
    tx = Transaccion.query.get(tx_id)
    if tx:
        tx.estado = 'COMPLETADO'
        db.session.commit()
        flash("Retiro completado.")
    return redirect(url_for('admin_panel'))

@app.route('/banear_usuario/<int:u_id>', methods=['POST'])
@login_required
def banear_usuario(u_id):
    if current_user.username != 'Cristhian2704': return redirect(url_for('dashboard'))
    u = User.query.get(u_id)
    if u and u.username == 'Cristhian2704':
        flash("No puedes banear la cuenta maestra.")
        return redirect(url_for('admin_panel'))
    if u:
        u.deposito_status = 'BANEADO'
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/ajuste_manual', methods=['POST'])
@login_required
def ajuste_manual():
    if current_user.username != 'Cristhian2704': return redirect(url_for('dashboard'))
    u = User.query.get(request.form.get('user_id'))
    if u:
        u.balance = float(request.form.get('nuevo_balance'))
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/solicitar_retiro', methods=['POST'])
@login_required
def solicitar_retiro():
    if datetime.now().weekday() != 5:
        flash("Retiros solo Sábados.")
        return redirect(url_for('retirar'))
    try:
        monto = float(request.form.get('monto', 0))
        if monto >= 10 and monto <= current_user.roi_total:
            db.session.add(Transaccion(tipo='RETIRO', monto=monto, fee=monto*0.05, estado='PENDIENTE', user_id=current_user.id))
            current_user.roi_total -= monto
            db.session.commit()
            flash("Solicitud enviada.")
    except: flash("Error.")
    return redirect(url_for('dashboard'))

@app.route('/terminos')
def terminos(): return render_template('terminos.html')

@app.route('/privacidad')
def privacidad(): return render_template('privacidad.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run()