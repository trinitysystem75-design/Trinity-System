import os
import random
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
from sqlalchemy import func
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler

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
    saldo_tareas = db.Column(db.Float, default=0.0)
    transacciones = db.relationship('Transaccion', backref='dueno', lazy=True)

class Transaccion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.Text) 
    monto = db.Column(db.Float)    
    fee = db.Column(db.Float, default=0.0) 
    comprobante = db.Column(db.Text, nullable=True) 
    fecha = db.Column(db.DateTime, default=datetime.now) 
    estado = db.Column(db.Text, default='PENDIENTE') 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class TareasCompletadas(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tarea_id = db.Column(db.String(100), nullable=False)
    monto_pagado = db.Column(db.Float, default=0.0)
    estado = db.Column(db.String(20), default="Aprobado")
    fecha = db.Column(db.DateTime, default=datetime.now)

# --- LÓGICA DE ROI DIARIO (SOLO LUNES A VIERNES) ---
def repartir_roi_diario():
    with app.app_context():
        # Filtro de seguridad interno por si se llama la función manualmente
        if datetime.now().weekday() > 4: 
            print(f"Fin de semana detectado. No se reparte ROI.")
            return

        usuarios = User.query.filter(User.balance > 0, User.deposito_status == 'ACTIVO').all()
        for u in usuarios:
            ganancia = round(u.balance * 0.012, 2)
            u.roi_total += ganancia
            db.session.add(Transaccion(
                tipo='ROI', 
                monto=ganancia, 
                estado='OK', 
                comprobante='', 
                user_id=u.id,
                fecha=datetime.now()
            ))
        db.session.commit()
        print(f"ROI automático repartido: {datetime.now()}")

# --- SCHEDULER (Configurado para días hábiles) ---
scheduler = BackgroundScheduler()
scheduler.add_job(func=repartir_roi_diario, trigger="cron", day_of_week='mon-fri', hour=0, minute=0)
scheduler.start()

# Forzamos la creación de carpetas y actualización de BD al inicio
with app.app_context():
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    db.create_all()
    
    try:
        db.session.execute(db.text("ALTER TABLE tareas_completadas ADD COLUMN monto_pagado FLOAT DEFAULT 0.0;"))
        db.session.commit()
    except:
        db.session.rollback()
        
    if "postgresql" in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
        try:
            db.session.execute(db.text("ALTER TABLE transaccion ALTER COLUMN tipo TYPE TEXT;"))
            db.session.execute(db.text("ALTER TABLE transaccion ALTER COLUMN estado TYPE TEXT;"))
            db.session.execute(db.text("ALTER TABLE transaccion ALTER COLUMN comprobante TYPE TEXT;"))
            db.session.commit()
        except:
            db.session.rollback()

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    if user and user.deposito_status == 'BANEADO': return None
    return user

# --- RUTAS DE NAVEGACIÓN GENERAL ---
@app.route('/')
def home(): 
    return render_template('index.html')

@app.route('/login')
def login(): return render_template('login.html')

@app.route('/registro')
def registro():
    ref_id = request.args.get('ref')
    return render_template('registro.html', ref_id=ref_id)

@app.route('/crear_usuario', methods=['POST'])
def crear_usuario():
    u, e, p = request.form.get('username'), request.form.get('email'), request.form.get('password')
    ref = request.args.get('ref')
    clean_ref = int(ref) if ref and ref.isdigit() else None
    
    if User.query.filter_by(username=u).first() or User.query.filter_by(email=e).first():
        flash("Usuario o correo ya registrado.")
        return redirect(url_for('registro'))

    codigo = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    try:
        msg = Message("Código de Verificación", sender="trinitysystem75@gmail.com", recipients=[e])
        msg.body = f"Tu código es: {codigo}"
        mail.send(msg)
    except: pass
    
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
    if user and user.esta_verificado and user.deposito_status != 'BANEADO':
        login_user(user)
        return redirect(url_for('dashboard'))
    flash("Error de acceso.")
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
        if monto >= 30 and 'comprobante' in request.files:
            file = request.files['comprobante']
            if file and file.filename != '':
                ext = file.filename.split('.')[-1]
                fn = f"dep_{current_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                current_user.deposito_status = 'PENDIENTE'
                db.session.add(Transaccion(tipo='DEPÓSITO', monto=monto, comprobante=fn, user_id=current_user.id, fecha=datetime.now()))
                db.session.commit()
                flash("Pago enviado.")
    except: flash("Error.")
    return redirect(url_for('dashboard'))

# --- SISTEMA DE MISIONES Y ANUNCIOS ---

@app.route('/panel/tareas')
@login_required
def panel_tareas():
    tareas_realizadas = TareasCompletadas.query.filter_by(usuario_id=current_user.id, estado='Aprobado').count()
    ganancia_acumulada = current_user.saldo_tareas
    link_ref = f"{DOMINIO_OFICIAL}/registro?ref={current_user.id}"
    return render_template('tareas.html', link_ref=link_ref, tareas_realizadas=tareas_realizadas, ganancia_acumulada=ganancia_acumulada)

@app.route('/retiro_tareas', methods=['POST'])
@login_required
def retiro_tareas():
    if datetime.now().weekday() != 5:
        flash("Los retiros de misiones solo están habilitados los días Sábados.")
        return redirect(url_for('panel_tareas'))
    
    try:
        monto = float(request.form.get('monto', 0))
        nombre = request.form.get('nombre')
        binance_id = request.form.get('binance_id')
        
        if monto >= 5.0 and monto <= current_user.saldo_tareas:
            fee_monto = round(monto * 0.05, 2) # Fee del 5% aplicado a las misiones
            detalles_pago = f"Binance ID: {binance_id} | Titular: {nombre}"
            
            nueva_tx = Transaccion(
                tipo='RETIRO_TAREAS', 
                monto=monto, 
                fee=fee_monto,
                estado='PENDIENTE', 
                comprobante=detalles_pago, 
                user_id=current_user.id, 
                fecha=datetime.now()
            )
            current_user.saldo_tareas -= monto
            db.session.add(nueva_tx)
            db.session.commit()
            flash("✅ ¡Solicitud de retiro enviada exitosamente! En breve la procesaremos.")
        else:
            flash("❌ Saldo insuficiente o monto menor al límite mínimo estipulado ($5.00 USD).")
    except:
        flash("❌ Hubo un error al procesar la solicitud.")
        
    return redirect(url_for('panel_tareas'))

@app.route('/webhook/reward', methods=['GET', 'POST'])
def webhook_reward():
    token_seguridad = request.args.get('secret')
    if token_seguridad != 'trinity_secure_2026':
        return "Acceso denegado. Token inválido.", 403
        
    user_id = request.args.get('user_id')
    monto = request.args.get('monto')
    tarea_id = request.args.get('tarea_id', 'Oferta_Automatica')
    
    if user_id and monto:
        user = User.query.get(int(user_id))
        if user:
            try:
                valor_monto = float(monto)
                user.saldo_tareas += valor_monto
                registro_mision = TareasCompletadas(
                    usuario_id=user.id,
                    tarea_id=tarea_id,
                    monto_pagado=valor_monto,
                    estado='Aprobado'
                )
                db.session.add(registro_mision)
                db.session.commit()
                return "OK", 200
            except:
                db.session.rollback()
                return "Error procesando el monto numérico.", 400
    return "Datos incompletos.", 400

# --- PANEL ADMIN CONTROLES ---

@app.route('/system-root-portal')
@login_required
def admin_panel():
    if current_user.username != 'Cristhian2704': return redirect(url_for('dashboard'))
    usuarios = User.query.all()
    pagos = Transaccion.query.filter_by(estado='PENDIENTE', tipo='DEPÓSITO').all()
    
    retiros = Transaccion.query.filter_by(estado='PENDIENTE', tipo='RETIRO').all()
    retiros_tareas = Transaccion.query.filter_by(estado='PENDIENTE', tipo='RETIRO_TAREAS').all()
    
    cap_total = db.session.query(func.sum(User.balance)).scalar() or 0.0
    roi_pagar = db.session.query(func.sum(User.roi_total)).scalar() or 0.0
    
    return render_template('admin_trinity.html', usuarios=usuarios, pagos=pagos, retiros=retiros, retiros_tareas=retiros_tareas, capital_total=cap_total, roi_por_pagar=roi_pagar)

@app.route('/admin/pagar-roi', methods=['POST'])
@login_required
def pagar_roi_manual():
    if current_user.username != 'Cristhian2704': return "No autorizado."
    usuarios = User.query.filter_by(deposito_status='ACTIVO').filter(User.balance > 0).all()
    contador = 0
    try:
        for u in usuarios:
            ganancia = round(u.balance * 0.012, 2)
            u.roi_total += ganancia
            db.session.add(Transaccion(
                tipo='ROI', 
                monto=ganancia, 
                estado='OK', 
                comprobante='', 
                user_id=u.id,
                fecha=datetime.now()
            ))
            contador += 1
        db.session.commit()
        flash(f"Éxito: {contador} ROIs pagados.")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {str(e)}")
    return redirect(url_for('admin_panel'))

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
                bono = round(tx.monto * 0.10, 2)
                patro.roi_total += bono 
                db.session.add(Transaccion(tipo='BONO_RED', monto=bono, estado='OK', comprobante='', user_id=patro.id, fecha=datetime.now()))
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/aprobar_retiro/<int:tx_id>', methods=['POST'])
@login_required
def aprobar_retiro(tx_id):
    if current_user.username != 'Cristhian2704': return redirect(url_for('dashboard'))
    tx = Transaccion.query.get(tx_id)
    if tx:
        tx.estado = 'COMPLETADO'
        db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/banear_usuario/<int:u_id>', methods=['POST'])
@login_required
def banear_usuario(u_id):
    if current_user.username != 'Cristhian2704': return redirect(url_for('dashboard'))
    u = User.query.get(u_id)
    if u and u.username != 'Cristhian2704':
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
        flash("Los retiros de ROI solo están habilitados los días Sábados.")
        return redirect(url_for('retirar'))
    try:
        monto = float(request.form.get('monto', 0))
        nombre_binance = request.form.get('nombre_binance', '')
        binance_id = request.form.get('binance_id', '')

        if monto >= 5 and monto <= current_user.roi_total:
            fee_monto = round(monto * 0.05, 2)
            detalles_retiro = f"Binance: {binance_id} | Nombre: {nombre_binance}"
            
            nueva_tx = Transaccion(
                tipo='RETIRO', 
                monto=monto, 
                fee=fee_monto, 
                estado='PENDIENTE', 
                comprobante=detalles_retiro, 
                user_id=current_user.id, 
                fecha=datetime.now()
            )
            current_user.roi_total -= monto
            db.session.add(nueva_tx)
            db.session.commit()
            flash("✅ Solicitud de retiro enviada correctamente.")
        else:
            flash("❌ Saldo insuficiente o no cumples con el mínimo de $5.")
    except: 
        flash("❌ Error al procesar tu solicitud.")
    return redirect(url_for('retirar'))

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
    app.run(debug=True)