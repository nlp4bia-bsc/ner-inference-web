"""Complete auth vocabulary; stable keys, allowlisted locales and English fallback."""

# Each row is English | Spanish | Catalan. Profile/role codes never drive privileges.
ROWS = {
    "service_unavailable": (
        "The service is temporarily unavailable. Please try again later.",
        "El servicio no está disponible temporalmente. Inténtalo más tarde.",
        "El servei no està disponible temporalment. Torna-ho a provar més tard.",
    ),
    "previous": ("Previous", "Anterior", "Anterior"),
    "next": ("Next", "Siguiente", "Següent"),
    "login": ("Sign in", "Iniciar sesión", "Inicia la sessió"),
    "register": ("Create account", "Crear cuenta", "Crea un compte"),
    "logout": ("Sign out", "Cerrar sesión", "Tanca la sessió"),
    "logout_all": ("Sign out everywhere", "Cerrar todas las sesiones", "Tanca totes les sessions"),
    "full_name": ("Full name", "Nombre completo", "Nom complet"),
    "email": ("Email", "Email", "Correu electrònic"),
    "institution": (
        "Institution or organization",
        "Institución u organización",
        "Institució o organització",
    ),
    "professional_role": (
        "Professional activity",
        "Actividad profesional",
        "Activitat professional",
    ),
    "professional_role_other": (
        "Describe your activity",
        "Describe tu actividad",
        "Descriu la teva activitat",
    ),
    "CLINICIAN": (
        "Clinician / Healthcare Professional",
        "Profesional clínico / sanitario",
        "Professional clínic / sanitari",
    ),
    "RESEARCHER": ("Researcher", "Investigador/a", "Investigador/a"),
    "DATA_SCIENTIST": ("Data Scientist", "Científico/a de datos", "Científic/a de dades"),
    "NLP_ENGINEER": (
        "NLP Engineer / Bioinformatician",
        "Ingeniero/a de PLN / Bioinformático/a",
        "Enginyer/a de PLN / Bioinformàtic/a",
    ),
    "STUDENT": ("Student / PhD Candidate", "Estudiante / Doctorando/a", "Estudiant / Doctorand/a"),
    "OTHER": ("Other", "Otra", "Altra"),
    "password": ("Password", "Contraseña", "Contrasenya"),
    "password_confirmation": (
        "Confirm password",
        "Confirmar contraseña",
        "Confirma la contrasenya",
    ),
    "current_password": ("Current password", "Contraseña actual", "Contrasenya actual"),
    "password_hint": (
        "Use 4–1024 characters. Spaces and password managers are supported.",
        "Usa entre 4 y 1024 caracteres. Se admiten espacios y gestores de contraseñas.",
        "Utilitza entre 4 i 1024 caràcters. S'admeten espais i gestors de contrasenyes.",
    ),
    "legal_accepted": (
        "I acknowledge the research use and privacy notices below.",
        "He leído los avisos de uso académico y privacidad siguientes.",
        "He llegit els avisos d'ús acadèmic i privacitat següents.",
    ),
    "legal_notice": (
        "Research use only. Upload only data you are authorized to process. Account data remains until managed by the institution; job files expire 72 hours after completion. The institution must supply its applicable legal notices before production.",
        "Solo uso académico. Sube únicamente datos que estés autorizado a procesar. Los datos de cuenta permanecen hasta su gestión institucional; los archivos de trabajos caducan 72 horas después de finalizar. La institución debe aportar sus avisos legales antes de producción.",
        "Només ús acadèmic. Puja únicament dades que estiguis autoritzat a processar. Les dades del compte romanen fins a la gestió institucional; els fitxers dels treballs caduquen 72 hores després de finalitzar. La institució ha d'aportar els avisos legals abans de producció.",
    ),
    "forgot": ("Forgot password", "Recuperar contraseña", "Recupera la contrasenya"),
    "reset": ("Reset password", "Restablecer contraseña", "Restableix la contrasenya"),
    "verify": ("Verify email", "Verificar email", "Verifica el correu"),
    "resend": ("Resend verification", "Reenviar verificación", "Torna a enviar la verificació"),
    "change_password": ("Change password", "Cambiar contraseña", "Canvia la contrasenya"),
    "save": ("Save changes", "Guardar cambios", "Desa els canvis"),
    "dashboard": ("My dashboard", "Mi panel", "El meu tauler"),
    "profile": ("My profile", "Mi perfil", "El meu perfil"),
    "new_job": ("New annotation job", "Nuevo trabajo de anotación", "Nou treball d'anotació"),
    "jobs": ("My jobs", "Mis trabajos", "Els meus treballs"),
    "empty": ("You have no jobs yet.", "Todavía no tienes trabajos.", "Encara no tens treballs."),
    "tier": ("Access tier", "Nivel de acceso", "Nivell d'accés"),
    "limit": ("Documents per job", "Documentos por trabajo", "Documents per treball"),
    "unlimited": (
        "No administrative count limit; technical limits still apply",
        "Sin límite administrativo de documentos; se mantienen los límites técnicos",
        "Sense límit administratiu de documents; es mantenen els límits tècnics",
    ),
    "created": ("Created", "Creación", "Creació"),
    "expires": ("Expires", "Caducidad", "Caducitat"),
    "status": ("Status", "Estado", "Estat"),
    "progress": ("Progress", "Progreso", "Progrés"),
    "open": ("Open job", "Abrir trabajo", "Obre el treball"),
    "viewer": ("Viewer", "Visualizador", "Visualitzador"),
    "download": ("Downloads", "Descargas", "Descàrregues"),
    "verification_required": (
        "Verify your email before submitting jobs.",
        "Verifica tu email antes de enviar trabajos.",
        "Verifica el correu abans d'enviar treballs.",
    ),
    "authentication_required": (
        "Sign in to continue.",
        "Inicia sesión para continuar.",
        "Inicia la sessió per continuar.",
    ),
    "invalid_credentials": (
        "Invalid credentials or account unavailable.",
        "Credenciales incorrectas o cuenta no disponible.",
        "Credencials incorrectes o compte no disponible.",
    ),
    "invalid_form": (
        "Check the fields, password confirmation and required notices.",
        "Revisa los campos, la confirmación y los avisos obligatorios.",
        "Revisa els camps, la confirmació i els avisos obligatoris.",
    ),
    "invalid_token": (
        "This link is invalid, expired or already used.",
        "El enlace no es válido, ha caducado o ya se ha utilizado.",
        "L'enllaç no és vàlid, ha caducat o ja s'ha utilitzat.",
    ),
    "csrf_failed": (
        "The security check failed. Reload the page and try again.",
        "La comprobación de seguridad ha fallado. Recarga la página e inténtalo de nuevo.",
        "La comprovació de seguretat ha fallat. Torna a carregar la pàgina i prova-ho de nou.",
    ),
    "origin_mismatch": (
        "The service address does not match its configuration. Contact the administrator.",
        "La dirección del servicio no coincide con su configuración. Contacta con el administrador.",
        "L'adreça del servei no coincideix amb la seva configuració. Contacta amb l'administrador.",
    ),
    "forbidden": (
        "You do not have permission for this operation.",
        "No tienes permiso para esta operación.",
        "No tens permís per a aquesta operació.",
    ),
    "mfa_required": (
        "Set up administrator MFA before opening administration.",
        "Configura el MFA de administrador antes de acceder a administración.",
        "Configura l'MFA d'administrador abans d'accedir a administració.",
    ),
    "mail_unavailable": (
        "Email delivery is unavailable. Contact the service administrator.",
        "El envío de correo no está disponible. Contacta con administración.",
        "L'enviament de correu no està disponible. Contacta amb administració.",
    ),
    "account_created": (
        "Account created. You can sign in now; no email verification is required.",
        "Cuenta creada. Ya puedes iniciar sesión; no se requiere verificación por correo.",
        "Compte creat. Ja pots iniciar la sessió; no cal verificació per correu.",
    ),
    "email_registered": (
        "This email is already registered. Sign in or contact the administrator.",
        "Este correo ya está registrado. Inicia sesión o contacta con el administrador.",
        "Aquest correu ja està registrat. Inicia la sessió o contacta amb l'administrador.",
    ),
    "email_sent": (
        "If this address is eligible, a message with the next steps has been sent.",
        "Si la dirección es válida para esta operación, se ha enviado un mensaje con los siguientes pasos.",
        "Si l'adreça és vàlida per a aquesta operació, s'ha enviat un missatge amb els passos següents.",
    ),
    "verified": (
        "Email verified. You can now sign in.",
        "Email verificado. Ya puedes iniciar sesión.",
        "Correu verificat. Ja pots iniciar la sessió.",
    ),
    "password_changed": (
        "Password updated. Sign in again.",
        "Contraseña actualizada. Inicia sesión de nuevo.",
        "Contrasenya actualitzada. Torna a iniciar la sessió.",
    ),
    "saved": ("Changes saved.", "Cambios guardados.", "Canvis desats."),
    "rate_limited": (
        "Too many attempts. Please try again later.",
        "Demasiados intentos. Inténtalo más tarde.",
        "Massa intents. Torna-ho a provar més tard.",
    ),
    "otp": (
        "Authenticator code or recovery code",
        "Código del autenticador o de recuperación",
        "Codi de l'autenticador o de recuperació",
    ),
    "mfa": ("Multi-factor authentication", "Autenticación multifactor", "Autenticació multifactor"),
    "mfa_start": ("Set up authenticator", "Configurar autenticador", "Configura l'autenticador"),
    "mfa_confirm": (
        "Confirm authenticator code",
        "Confirmar código del autenticador",
        "Confirma el codi de l'autenticador",
    ),
    "mfa_hint": (
        "Add this secret to your authenticator. Keep it private.",
        "Añade este secreto a tu autenticador. Mantenlo privado.",
        "Afegeix aquest secret al teu autenticador. Mantén-lo privat.",
    ),
    "recovery_codes": (
        "Save these one-use recovery codes now. They will not be shown again.",
        "Guarda ahora estos códigos de recuperación de un solo uso. No se volverán a mostrar.",
        "Desa ara aquests codis de recuperació d'un sol ús. No es tornaran a mostrar.",
    ),
    "mfa_enabled": ("Authenticator enabled", "Autenticador activado", "Autenticador activat"),
    "rotate": ("Rotate session", "Rotar sesión", "Rota la sessió"),
    "admin": ("Administration", "Administración", "Administració"),
    "search": (
        "Search email or institution",
        "Buscar email o institución",
        "Cerca correu o institució",
    ),
    "verification": ("Email verification", "Verificación del email", "Verificació del correu"),
    "yes": ("Yes", "Sí", "Sí"),
    "no": ("No", "No", "No"),
    "QUEUED": ("Queued", "En cola", "En cua"),
    "PROCESSING": ("Processing", "En proceso", "En procés"),
    "COMPLETED": ("Completed", "Completado", "Completat"),
    "COMPLETED_WITH_ERRORS": (
        "Completed with errors",
        "Completado con errores",
        "Completat amb errors",
    ),
    "FAILED": ("Failed", "Fallido", "Fallit"),
    "EXPIRED": ("Expired", "Caducado", "Caducat"),
    "ACTIVE": ("Active", "Activa", "Actiu"),
    "SUSPENDED": ("Suspended", "Suspendida", "Suspès"),
    "verify_subject": (
        "Verify your NLP4BIA email",
        "Verifica tu email de NLP4BIA",
        "Verifica el correu de NLP4BIA",
    ),
    "reset_subject": (
        "Reset your NLP4BIA password",
        "Restablece tu contraseña de NLP4BIA",
        "Restableix la contrasenya de NLP4BIA",
    ),
    "email_body": (
        "Open this link and confirm the operation. It expires and can be used once. If you did not request this, ignore this email.",
        "Abre este enlace y confirma la operación. Caduca y solo puede utilizarse una vez. Si no lo has solicitado, ignora este correo.",
        "Obre aquest enllaç i confirma l'operació. Caduca i només es pot utilitzar una vegada. Si no ho has sol·licitat, ignora aquest correu.",
    ),
    "audit": (
        "Administrative audit history",
        "Historial de auditoría administrativa",
        "Historial d'auditoria administrativa",
    ),
    "revoke": ("Revoke sessions", "Revocar sesiones", "Revoca les sessions"),
    "system_role": ("System role", "Rol del sistema", "Rol del sistema"),
    "metrics": ("Operational totals", "Totales operativos", "Totals operatius"),
    "last_admin": (
        "The last active administrator cannot be removed.",
        "No se puede retirar al último administrador activo.",
        "No es pot retirar l'últim administrador actiu.",
    ),
}


def locale(value):
    return value if value in ("en", "es", "ca") else "en"


def translate(key, language="en"):
    return ROWS.get(key, (key, key, key))[("en", "es", "ca").index(locale(language))]
