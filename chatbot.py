from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

# Firebase setup
cred = credentials.Certificate("firebase_config.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Estados por usuario
user_stage = {}  # para registro de interés y provincia
user_state = {}  # para flujo de consultas
user_context = {}  # para almacenar último cantón o provincia consultada

# Menús
main_menu = [
    ["📍 Votantes por Cantón", "🏛️ Votantes por Provincia"],
    ["🧮 Juntas Receptoras", "🌎 Votantes en el Exterior"],
    ["🏘️ Zonas de residencia por Cantón"]
]
juntas_menu = [
    ["📍 Juntas por Cantón", "🏛️ Juntas por Provincia"],
    ["⬅️ Atrás"]
]
interes_menu = [
    ["Ciudadano/a", "Parte de una campaña electoral"],
    ["Trabajo en GAD o institución pública", "Periodista o investigador/a"],
    ["Otro"]
]
interes_keyboard = ReplyKeyboardMarkup(interes_menu, resize_keyboard=True)
provincias_ecuador = [
    "Azuay", "Bolívar", "Cañar", "Carchi", "Chimborazo", "Cotopaxi", "El Oro", "Esmeraldas",
    "Galápagos", "Guayas", "Imbabura", "Loja", "Los Ríos", "Manabí", "Morona Santiago",
    "Napo", "Orellana", "Pastaza", "Pichincha", "Santa Elena", "Santo Domingo de los Tsáchilas",
    "Sucumbíos", "Tungurahua", "Zamora Chinchipe"
]
prov_keyboard = ReplyKeyboardMarkup(
    [[prov] for prov in provincias_ecuador] + [["⬅️ Atrás"]],
    resize_keyboard=True
)
main_keyboard = ReplyKeyboardMarkup(main_menu, resize_keyboard=True)
juntas_keyboard = ReplyKeyboardMarkup(juntas_menu, resize_keyboard=True)

def generar_submenu(tipo):
    if tipo == "votantes_exterior":
        return ReplyKeyboardMarkup([
            ["🏠 Volver al Menú Principal", "🚪 Terminar la Conversación"]
        ], resize_keyboard=True)
    elif tipo in ["juntas_canton", "juntas_provincia"]:
        return ReplyKeyboardMarkup([
            ["🌆 Ver por Zona"],
            ["🏠 Volver al Menú Principal", "🚪 Terminar la Conversación"]
        ], resize_keyboard=True)
    elif tipo == "residencia_canton":
        return ReplyKeyboardMarkup([
            ["🔍 Ver por Sexo"],
            ["🏠 Volver al Menú Principal", "🚪 Terminar la Conversación"]
        ], resize_keyboard=True)
    else:
        return ReplyKeyboardMarkup([
            ["🔍 Ver por Sexo", "🌆 Ver por Zona"],
            ["🏠 Volver al Menú Principal", "🚪 Terminar la Conversación"]
        ], resize_keyboard=True)

# Guardar usuario en Firebase (modo historial)
def registrar_usuario(user_id, interes, provincia):
    historial_ref = db.collection("usuarios_historial")
    historial = historial_ref.where("user_id", "==", user_id).stream()
    contador = sum(1 for _ in historial) + 1
    doc_id = f"{user_id}_{contador}"
    historial_ref.document(doc_id).set({
        "user_id": user_id,
        "interes": interes,
        "provincia": provincia,
        "registro_n": contador,
        "fecha_registro": datetime.now().isoformat()
    })

# Utilidades de consulta
def get_total(field_name, field_value, count_field):
    docs = db.collection("electores").where(f"`{field_name}`", "==", field_value).stream()
    total = sum(int(doc.to_dict().get(count_field, 0) or 0) for doc in docs)
    return total

# Contacto institucional
async def terminar_conversacion(update: Update):
    await update.message.reply_text(
        "¿Te interesa un análisis más detallado?\n"
        "- Visita https://ciees.com.ec\n"
        "- Síguenos en redes sociales:\n"
        "LinkedIn: CIEES\n"
        "X: @CIEESec\n"
        "Facebook: CIEES"
    )

# Inicio
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_stage[user_id] = {"stage": "interes"}
    await update.message.reply_text(
        "👋 Bienvenida\n"
        "Chat Electoral de CIEES.\n"
        "Información electoral de las 24 provincias y 221 cantones del Ecuador\n"
        "(Padrón 2025, corte: 25 de agosto de 2024).\n\n"
        "¿Cuál es tu interés principal?",
        reply_markup=interes_keyboard
    )

# Manejo de mensajes
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if text.lower() in ["hola", "/start"]:
        await start(update, context)
        return

    if user_id in user_stage:
        stage_info = user_stage[user_id]

        if stage_info["stage"] == "interes":
            if text not in sum(interes_menu, []):
                await update.message.reply_text("Por favor, selecciona una opción del menú.")
                return
            user_stage[user_id]["interes"] = text
            user_stage[user_id]["stage"] = "provincia"
            await update.message.reply_text("¿Desde qué provincia te contactas?", reply_markup=prov_keyboard)
            return

        elif stage_info["stage"] == "provincia":
            if text == "⬅️ Atrás":
                user_stage[user_id]["stage"] = "interes"
                await update.message.reply_text("¿Cuál es tu interés principal?", reply_markup=interes_keyboard)
                return
            if text not in provincias_ecuador:
                await update.message.reply_text("Por favor, selecciona una provincia válida.")
                return
            interes = user_stage[user_id]["interes"]
            registrar_usuario(user_id, interes, text)
            user_stage.pop(user_id)
            await update.message.reply_text(f"✅ Registro completado como *{interes}* desde *{text}*.", parse_mode="Markdown")
            await update.message.reply_text("Selecciona una opción para continuar:", reply_markup=main_keyboard)
            return

    if text == "📍 Votantes por Cantón":
        user_state[user_id] = "votantes_canton"
        await update.message.reply_text("✍️ Escribe el nombre del cantón:")
        return

    elif text == "🏛️ Votantes por Provincia":
        user_state[user_id] = "votantes_provincia"
        await update.message.reply_text("✍️ Escribe el nombre de la provincia:")
        return

    elif text == "🧮 Juntas Receptoras":
        await update.message.reply_text("Selecciona una opción:", reply_markup=juntas_keyboard)
        return

    elif text == "📍 Juntas por Cantón":
        user_state[user_id] = "juntas_canton"
        await update.message.reply_text("✍️ Escribe el nombre del cantón:")
        return

    elif text == "🏛️ Juntas por Provincia":
        user_state[user_id] = "juntas_provincia"
        await update.message.reply_text("✍️ Escribe el nombre de la provincia:")
        return

    elif text == "🌎 Votantes en el Exterior":
        total = get_total("Estado Parroquia", "E", "Número de Electores")
        await update.message.reply_text(f"🌍 Total de votantes en el exterior: {total:,}")
        user_context[user_id] = {"tipo": "exterior", "valor": "E"}
        user_state[user_id] = "submenu"
        await update.message.reply_text("Selecciona una de las siguientes opciones:", reply_markup=generar_submenu("votantes_exterior"))
        return


    elif text == "🏘️ Zonas de residencia por Cantón":
        user_state[user_id] = "residencia_canton"
        await update.message.reply_text("✍️ Escribe el nombre del cantón:")
        return


    # --- Procesamiento de respuestas ---
    if user_state.get(user_id) == "votantes_canton":
        total = get_total("Nombre Cantón", text.upper(), "Número de Electores")
        if total > 0:
            await update.message.reply_text(f"✅ En el cantón {text.title()} votan {total:,} personas.")
            user_context[user_id] = {"tipo": "cantón", "valor": text.upper()}
            user_state[user_id] = "submenu"
            await update.message.reply_text("¿Deseas saber más detalles?", reply_markup=generar_submenu("votantes_canton"))
        else:
            await update.message.reply_text("❌ Lo siento, este cantón no existe. Inténtalo nuevamente o escribe 'Atrás' para volver al menú.")
        return

    elif user_state.get(user_id) == "votantes_provincia":
        total = get_total("Nombre Provincia", text.upper(), "Número de Electores")
        if total > 0:
            await update.message.reply_text(f"✅ En la provincia de {text.title()} votan {total:,} personas.")
            user_context[user_id] = {"tipo": "provincia", "valor": text.upper()}
            user_state[user_id] = "submenu"
            await update.message.reply_text("¿Deseas saber más detalles?", reply_markup=generar_submenu("votantes_provincia"))
        else:
            await update.message.reply_text("❌ Lo siento, esta provincia no existe. Inténtalo nuevamente o escribe 'Atrás' para volver al menú.")
        return

    elif user_state.get(user_id) == "juntas_canton":
        total = get_total("Nombre Cantón", text.upper(), "Número de Juntas")
        if total > 0:
            await update.message.reply_text(f"🗳️ En el cantón {text.title()} hay {total:,} juntas receptoras del voto.")
            user_context[user_id] = {"tipo": "cantón", "valor": text.upper(), "modo": "juntas"}
            user_state[user_id] = "submenu"
            await update.message.reply_text("¿Deseas saber más detalles?", reply_markup=generar_submenu("juntas_canton"))
        else:
            await update.message.reply_text("❌ Este cantón no existe. Inténtalo nuevamente o escribe 'Atrás' para volver al menú.")
        return

    elif user_state.get(user_id) == "juntas_provincia":
        total = get_total("Nombre Provincia", text.upper(), "Número de Juntas")
        if total > 0:
            await update.message.reply_text(f"🗳️ En la provincia de {text.title()} hay {total:,} juntas receptoras del voto.")
            user_context[user_id] = {"tipo": "provincia", "valor": text.upper(), "modo": "juntas"}
            user_state[user_id] = "submenu"
            await update.message.reply_text("¿Deseas saber más detalles?", reply_markup=generar_submenu("juntas_provincia"))
        else:
            await update.message.reply_text("❌ Esta provincia no existe. Inténtalo nuevamente o escribe 'Atrás' para volver al menú.")
        return
    
    elif user_state.get(user_id) == "residencia_canton":
        docs = db.collection("electores").where("`Nombre Cantón`", "==", text.upper()).stream()
        urbanos, rurales = 0, 0
        for doc in docs:
            data = doc.to_dict()
            tipo = data.get("Estado Parroquia")
            electores = int(data.get("Número de Electores", 0) or 0)
            if tipo == "U":
                urbanos += electores
            elif tipo == "R":
                rurales += electores
        total = urbanos + rurales
        if total == 0:
            await update.message.reply_text("❌ Lo siento, este cantón no existe. Inténtalo nuevamente o escribe 'Atrás' para volver al menú.")
        else:
            await update.message.reply_text(
                f"🏘️ Zonas de Residencia en {text.title()}:\n"
                f"• Urbana: {urbanos:,}\n"
                f"• Rural: {rurales:,}\n"
                f"• Total: {total:,}"
            )
        user_context[user_id] = {"tipo": "cantón", "valor": text.upper()}
        user_state[user_id] = "submenu"
        await update.message.reply_text("¿Deseas saber más detalles?", reply_markup=generar_submenu("residencia_canton"))
        return

    # Submenú general
    if user_state.get(user_id) == "submenu":
        ctx = user_context.get(user_id, {})
        tipo = ctx.get("tipo")
        valor = ctx.get("valor")
        modo = ctx.get("modo", "electores")

        if text == "🔍 Ver por Sexo":
            if modo == "electores":
                hombres = get_total(f"Nombre {tipo.title()}", valor, "Número de Electores Hombres")
                mujeres = get_total(f"Nombre {tipo.title()}", valor, "Número de Electores Mujeres")
            else:
                hombres = get_total(f"Nombre {tipo.title()}", valor, "Juntas Hombres")
                mujeres = get_total(f"Nombre {tipo.title()}", valor, "Juntas Mujeres")
            await update.message.reply_text(f"👤 Hombres: {hombres:,}\n👩 Mujeres: {mujeres:,}")
            return

        elif text == "🌆 Ver por Zona":
            docs = db.collection("electores").where(f"`Nombre {tipo.title()}`", "==", valor).stream()
            urbanos = rurales = 0
            campo = "Número de Juntas" if modo == "juntas" else "Número de Electores"
            for doc in docs:
                data = doc.to_dict()
                if data.get("Estado Parroquia") == "U":
                    urbanos += int(data.get(campo, 0) or 0)
                elif data.get("Estado Parroquia") == "R":
                    rurales += int(data.get(campo, 0) or 0)
            await update.message.reply_text(
                f"🏘️ Distribución por Zona:\n"
                f"• Urbana: {urbanos:,}\n"
                f"• Rural: {rurales:,}\n"
                f"• Total: {urbanos + rurales:,}"
            )
            return

        elif text == "🏠 Volver al Menú Principal":
            user_state.pop(user_id, None)
            user_context.pop(user_id, None)
            await update.message.reply_text("Menú principal:", reply_markup=main_keyboard)
            return

        elif text == "🚪 Terminar la Conversación":
            user_state.pop(user_id, None)
            user_context.pop(user_id, None)
            await terminar_conversacion(update)
            return

    await update.message.reply_text("Escribe 'Hola' para iniciar o selecciona una opción del menú.")

# Ejecutar bot
if __name__ == "__main__":
    app = ApplicationBuilder().token("7658329214:AAEbFDirzsgR59Uzgg5elP01l7se39TZ310").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Bot en ejecución...")
    app.run_polling()
