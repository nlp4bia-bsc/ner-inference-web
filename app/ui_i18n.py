"""Shared UI vocabulary. English source | Spanish | Catalan; no document translation."""

from app.auth.i18n import ROWS as AUTH_ROWS
from app.locales import CODES, translated

_COPY = """
Normalization method|Método de normalización|Mètode de normalització
Exact string matching|Coincidencia exacta de texto|Coincidència exacta de text
Levenshtein|Levenshtein|Levenshtein
Similarity threshold|Umbral de similitud|Llindar de similitud
Use bi-encoder (slower)|Usar bi-encoder (más lento)|Utilitza el bi-encoder (més lent)
Bi-encoder encodes the terminology and may take a long time on first use.|El bi-encoder codifica la terminología y puede tardar mucho en el primer uso.|El bi-encoder codifica la terminologia i pot trigar molt en el primer ús.
Fast matching uses terminology strings. Levenshtein runs only when no exact match is found.|La búsqueda rápida compara textos del diccionario. Levenshtein se ejecuta solo si no hay coincidencia exacta.|La cerca ràpida compara textos del diccionari. Levenshtein només s'executa si no hi ha coincidència exacta.
Matching mentions|Buscando coincidencias de menciones|Cercant coincidències de mencions
Building lexical index|Construyendo índice léxico|Construint l'índex lèxic
Term-code pairs|Pares término-código|Parelles terme-codi
Bi-encoder|Bi-encoder|Bi-encoder
Select document|Seleccionar documento|Selecciona el document
Select all on this page|Seleccionar todos en esta página|Selecciona tots els d'aquesta pàgina
{count} selected|{count} seleccionados|{count} seleccionats
Delete selected documents ({count})|Eliminar documentos seleccionados ({count})|Elimina els documents seleccionats ({count})
This deletes only the selected documents and their annotations and frees your quota. Upload history remains.|Se eliminarán solo los documentos seleccionados y sus anotaciones y se liberará tu cuota. El historial de subidas se conserva.|S'eliminaran només els documents seleccionats i les seves anotacions i s'alliberarà la quota. Es conserva l'historial de càrregues.
Import terminology dictionaries before normalizing.|Importa los diccionarios terminológicos antes de normalizar.|Importa els diccionaris terminològics abans de normalitzar.
The terminology file is missing.|Falta el archivo terminológico.|Falta el fitxer terminològic.
No terminology is available for this language and entity.|No hay terminología disponible para este idioma y entidad.|No hi ha terminologia disponible per a aquest idioma i entitat.
No normalization encoder is configured.|No hay ningún encoder de normalización configurado.|No hi ha cap encoder de normalització configurat.
Concept normalization is disabled.|La normalización de conceptos está desactivada.|La normalització de conceptes està desactivada.
Concept normalization is unavailable.|La normalización de conceptos no está disponible.|La normalització de conceptes no està disponible.
Delete project|Eliminar proyecto|Elimina el projecte
Delete all documents|Eliminar todos los documentos|Elimina tots els documents
This deletes all documents, annotations and downloads in this project and frees your quota. Upload history remains.|Se eliminarán todos los documentos, anotaciones y descargas de este proyecto y se liberará tu cuota. El historial de subidas se conserva.|S'eliminaran tots els documents, anotacions i descàrregues del projecte i s'alliberarà la quota. Es conserva l'historial de càrregues.
This deletes all retained documents and annotations across your projects and frees your quota. Upload history remains.|Se eliminarán todos los documentos y anotaciones conservados en tus proyectos y se liberará tu cuota. El historial de subidas se conserva.|S'eliminaran tots els documents i anotacions conservats als projectes i s'alliberarà la quota. Es conserva l'historial de càrregues.
The link could not be copied.|No se ha podido copiar el enlace.|No s'ha pogut copiar l'enllaç.
Model inference progress|Progreso de inferencia de los modelos|Progrés d'inferència dels models
Loading model|Cargando modelo|Carregant el model
Encoding documents|Codificando documentos|Codificant documents
Preparing annotations|Preparando anotaciones|Preparant anotacions
Building terminology index|Construyendo índice terminológico|Construint l'índex terminològic
Loading terminology index|Cargando índice terminológico|Carregant l'índex terminològic
Waiting for terminology index|Esperando el índice terminológico|Esperant l'índex terminològic
Reading terminology|Leyendo terminología|Llegint terminologia
Writing terminology index|Guardando índice terminológico|Desant l'índex terminològic
Normalizing mentions|Normalizando menciones|Normalitzant mencions
Windows|Ventanas|Finestres
Terms|Términos|Termes
Batch|Lote|Lot
Pending|Pendiente|Pendent
Ready|Preparado|Preparat
Skipped|Omitido|Omès
Waiting for next batch|Esperando el siguiente lote|Esperant el lot següent
Processing service unavailable. Start the worker using the same configuration.|Servicio de procesamiento no disponible. Inicia el worker con la misma configuración.|Servei de processament no disponible. Inicia el worker amb la mateixa configuració.
The worker is processing another project.|El worker está procesando otro proyecto.|El worker està processant un altre projecte.
Clinical and Biomedical Text Annotation|Anotación de textos clínicos y biomédicos|Anotació de textos clínics i biomèdics
Developed by NLP4BIA · Barcelona Supercomputing Center|Desarrollado por NLP4BIA · Barcelona Supercomputing Center|Desenvolupat per NLP4BIA · Barcelona Supercomputing Center
Dashboard|Panel|Tauler
New annotation|Nueva anotación|Nova anotació
Models|Modelos|Models
Profile|Perfil|Perfil
Research Workspace|Espacio de investigación|Espai de recerca
Welcome back|Te damos la bienvenida|Et donem la benvinguda
Continue your annotation workflows, explore your results and manage your documents.|Continúa tus anotaciones, explora los resultados y gestiona tus documentos.|Continua les anotacions, explora els resultats i gestiona els documents.
Active jobs|Trabajos activos|Treballs actius
Completed jobs|Trabajos completados|Treballs completats
Results available|Resultados disponibles|Resultats disponibles
Your document limit|Tu límite de documentos|El teu límit de documents
Up to {count} documents per job|Hasta {count} documentos por trabajo|Fins a {count} documents per treball
Unlimited document count · Resource limits apply|Sin límite de documentos · Se aplican límites de recursos|Sense límit de documents · S'apliquen límits de recursos
Recent jobs|Trabajos recientes|Treballs recents
Browse my jobs|Ver mis trabajos|Consulta els meus treballs
View models|Ver modelos|Consulta els models
Manage profile|Gestionar perfil|Gestiona el perfil
Your research workspace is ready.|Tu espacio de investigación está listo.|El teu espai de recerca està preparat.
Start by annotating a text or uploading your first document collection.|Empieza anotando un texto o subiendo tu primera colección de documentos.|Comença anotant un text o pujant la primera col·lecció de documents.
Start your first annotation|Iniciar mi primera anotación|Inicia la primera anotació
Job|Trabajo|Treball
Language|Idioma|Llengua
Documents|Documentos|Documents
Document|Documento|Document
Open viewer|Abrir visor|Obre el visor
Explore annotations|Explorar anotaciones|Explora les anotacions
Research tools|Herramientas de investigación|Eines de recerca
Multilingual biomedical named entity recognition.|Reconocimiento multilingüe de entidades biomédicas.|Reconeixement multilingüe d'entitats biomèdiques.
From text to structured insight.|Del texto al conocimiento estructurado.|Del text al coneixement estructurat.
Annotate clinical and biomedical text, inspect every mention and export results for your research.|Anota textos clínicos y biomédicos, inspecciona cada mención y exporta los resultados para tu investigación.|Anota textos clínics i biomèdics, inspecciona cada menció i exporta els resultats per a la recerca.
Interactive annotations|Anotaciones interactivas|Anotacions interactives
Explore nested and overlapping entities in their original context.|Explora entidades anidadas y solapadas en su contexto original.|Explora entitats imbricades i superposades en el context original.
Multiple models|Múltiples modelos|Múltiples models
Choose language-specific and multilingual checkpoints explicitly.|Selecciona explícitamente modelos específicos por idioma y multilingües.|Selecciona explícitament models específics per llengua i multilingües.
Open research formats|Formatos abiertos de investigación|Formats oberts de recerca
BRAT and TSV exports for your annotation workflows.|Exportaciones BRAT y TSV para tus flujos de anotación.|Exportacions BRAT i TSV per als teus fluxos d'anotació.
Research access|Acceso para investigación|Accés de recerca
Sign in to your workspace|Accede a tu espacio de trabajo|Accedeix al teu espai de treball
Use your verified research account to continue.|Utiliza tu cuenta de investigación verificada para continuar.|Utilitza el compte de recerca verificat per continuar.
Use your research account to continue.|Utiliza tu cuenta de investigación para continuar.|Utilitza el compte de recerca per continuar.
Registered email|Correo registrado|Correu registrat
Password help: contact the administrator|Ayuda con la contraseña: contacta con el administrador|Ajuda amb la contrasenya: contacta amb l’administrador
Account help and error reports|Ayuda con la cuenta e incidencias|Ajuda amb el compte i incidències
New to the platform?|¿Primera vez en la plataforma?|És la primera visita a la plataforma?
Already have an account?|¿Ya tienes una cuenta?|Ja tens un compte?
Join the research workspace|Únete al espacio de investigación|Uneix-te a l'espai de recerca
New accounts start with a limit of 100 documents per job. Higher limits may be granted by the NLP4BIA team.|Las cuentas nuevas tienen un límite de 100 documentos por trabajo. El equipo NLP4BIA puede conceder límites superiores.|Els comptes nous tenen un límit de 100 documents per treball. L'equip NLP4BIA pot concedir límits superiors.
Show password|Mostrar contraseña|Mostra la contrasenya
Hide password|Ocultar contraseña|Amaga la contrasenya
Optional for accounts with an authenticator|Opcional para cuentas con autenticador|Opcional per a comptes amb autenticador
Sending…|Enviando…|S'està enviant…
Session expired. Sign in again to continue.|La sesión ha caducado. Inicia sesión de nuevo para continuar.|La sessió ha caducat. Torna a iniciar la sessió per continuar.
Account details|Datos de la cuenta|Dades del compte
Account security|Seguridad de la cuenta|Seguretat del compte
Verified email|Email verificado|Correu verificat
Email not yet verified|Email pendiente de verificación|Correu pendent de verificació
Active sessions|Sesiones activas|Sessions actives
Current session|Sesión actual|Sessió actual
Other session|Otra sesión|Una altra sessió
Last activity|Última actividad|Última activitat
Account deletion request|Solicitud de eliminación de cuenta|Sol·licitud d'eliminació del compte
Request account deletion|Solicitar eliminación de cuenta|Sol·licita l'eliminació del compte
This records a request for institutional review. It does not immediately delete your account or change job retention.|Se registrará una solicitud para revisión institucional. No elimina inmediatamente tu cuenta ni modifica la retención de trabajos.|Es registrarà una sol·licitud per a revisió institucional. No elimina immediatament el compte ni modifica la retenció dels treballs.
Your deletion request has been recorded for institutional review.|Tu solicitud de eliminación se ha registrado para revisión institucional.|La sol·licitud d'eliminació s'ha registrat per a revisió institucional.
Confirm change|Confirmar cambio|Confirma el canvi
Review this administrative action before applying it.|Revisa esta acción administrativa antes de aplicarla.|Revisa aquesta acció administrativa abans d'aplicar-la.
Confirm|Confirmar|Confirma
Cancel|Cancelar|Cancel·la
Close|Cerrar|Tanca
User management|Gestión de usuarios|Gestió d'usuaris
Manage accounts and access. Clinical documents remain private to their owners.|Gestiona cuentas y permisos. Los documentos clínicos permanecen privados para sus propietarios.|Gestiona comptes i permisos. Els documents clínics continuen sent privats per als propietaris.
Accounts|Cuentas|Comptes
Storage used|Almacenamiento utilizado|Emmagatzematge utilitzat
Failed emails|Correos fallidos|Correus fallits
Actions|Acciones|Accions
Audit history|Historial de auditoría|Historial d'auditoria
Search by email or institution|Buscar por email o institución|Cerca per correu o institució
Input documents|Documentos de entrada|Documents d'entrada
Entities and models|Entidades y modelos|Entitats i models
Review and submit|Revisar y enviar|Revisa i envia
Choose your input, document language and the checkpoints to run.|Elige la entrada, el idioma del documento y los modelos que ejecutar.|Tria l'entrada, la llengua del document i els models que cal executar.
Your plan allows up to {count} documents per request.|Tu nivel permite hasta {count} documentos por solicitud.|El teu nivell permet fins a {count} documents per sol·licitud.
Paste text|Pegar texto|Enganxa text
Upload TXT|Subir TXT|Puja TXT
Upload ZIP|Subir ZIP|Puja ZIP
Input mode|Modo de entrada|Mode d'entrada
Document text|Texto del documento|Text del document
Document name (optional)|Nombre del documento (opcional)|Nom del document (opcional)
Clear text|Borrar texto|Esborra el text
Copy text|Copiar texto|Copia el text
Drop documents here, or browse files|Arrastra documentos aquí o selecciona archivos|Arrossega documents aquí o selecciona fitxers
UTF-8 TXT · multiple files supported|TXT UTF-8 · se admiten múltiples archivos|TXT UTF-8 · s'admeten múltiples fitxers
One ZIP archive · nested TXT folders supported|Un archivo ZIP · se admiten carpetas con TXT|Un fitxer ZIP · s'admeten carpetes amb TXT
Maximum upload: {count} MB. Empty files and nested ZIPs are not supported.|Subida máxima: {count} MB. No se admiten archivos vacíos ni ZIP dentro de ZIP.|Pujada màxima: {count} MB. No s'admeten fitxers buits ni ZIP dins de ZIP.
No documents selected.|No hay documentos seleccionados.|No hi ha documents seleccionats.
Document language|Idioma del documento|Llengua del document
Use one language per batch.|Utiliza un idioma por lote.|Utilitza una llengua per lot.
Loading languages…|Cargando idiomas…|S'estan carregant les llengües…
Entity categories and models|Categorías de entidades y modelos|Categories d'entitats i models
Checking model availability…|Comprobando disponibilidad de modelos…|S'està comprovant la disponibilitat dels models…
Expand a category and choose one or more checkpoints.|Despliega una categoría y selecciona uno o varios modelos.|Desplega una categoria i selecciona un o diversos models.
No validated models are available for this language. Inference is currently unavailable.|No hay modelos validados para este idioma. La inferencia no está disponible actualmente.|No hi ha models validats per a aquesta llengua. La inferència no està disponible actualment.
Not available for this language|No disponible para este idioma|No disponible per a aquesta llengua
The model catalog could not be loaded. Please reload this page.|No se pudo cargar el catálogo de modelos. Recarga la página.|No s'ha pogut carregar el catàleg de models. Torna a carregar la pàgina.
The request could not be submitted. Please try again.|No se pudo enviar la solicitud. Inténtalo de nuevo.|No s'ha pogut enviar la sol·licitud. Torna-ho a provar.
Not validated for this document language.|No validado para el idioma del documento.|No validat per a la llengua del document.
Model information|Información del modelo|Informació del model
No independently verified metrics registered.|No hay métricas verificadas de forma independiente.|No hi ha mètriques verificades de manera independent.
Verified metrics|Métricas verificadas|Mètriques verificades
Multilingual models|Modelos multilingües|Models multilingües
See Multilingual models below for registered checkpoints.|Consulta los modelos registrados en Modelos multilingües.|Consulta els models registrats a Models multilingües.
No multilingual checkpoints registered.|No hay modelos multilingües registrados.|No hi ha models multilingües registrats.
{count} active|{count} activos|{count} actius
{count} model(s)|{count} modelo(s)|{count} model(s)
{count} characters · {bytes} UTF-8 bytes|{count} caracteres · {bytes} bytes UTF-8|{count} caràcters · {bytes} bytes UTF-8
{count} document(s)|{count} documento(s)|{count} document(s)
ZIP document count is checked by the server|El servidor comprueba el número de documentos del ZIP|El servidor comprova el nombre de documents del ZIP
None|Ninguna|Cap
Remove|Eliminar|Elimina
Submitting…|Enviando…|S'està enviant…
Uploading: {loaded} / {total} bytes|Subiendo: {loaded} / {total} bytes|S'estan pujant: {loaded} / {total} bytes
Upload complete. Validating and registering your request…|Subida completada. Validando y registrando tu solicitud…|Pujada completada. S'està validant i registrant la sol·licitud…
Upload progress|Progreso de subida|Progrés de la pujada
Start annotation|Iniciar anotación|Inicia l'anotació
Request accepted|Solicitud aceptada|Sol·licitud acceptada
Your documents have entered the persistent queue. Only your account can access this job.|Tus documentos han entrado en la cola persistente. Solo tu cuenta puede acceder a este trabajo.|Els documents han entrat a la cua persistent. Només el teu compte pot accedir a aquest treball.
Copy private link|Copiar enlace privado|Copia l'enllaç privat
Continue to request|Continuar al trabajo|Continua al treball
BRAT ZIP · TSV · Interactive explorer|BRAT ZIP · TSV · Visor interactivo|BRAT ZIP · TSV · Visor interactiu
Results remain available for {count} hours after processing. Only your account can access them.|Los resultados están disponibles durante {count} horas tras finalizar. Solo tu cuenta puede acceder a ellos.|Els resultats estan disponibles durant {count} hores després de finalitzar. Només el teu compte hi pot accedir.
Model catalog|Catálogo de modelos|Catàleg de models
Explore the registered models. Availability reflects local validation, not clinical accuracy.|Explora los modelos registrados. La disponibilidad refleja su validación local, no su precisión clínica.|Explora els models registrats. La disponibilitat reflecteix la validació local, no la precisió clínica.
Annotation explorer|Visor de anotaciones|Visualitzador d'anotacions
Request status|Estado del trabajo|Estat del treball
Download BRAT|Descargar BRAT|Descarrega BRAT
Download TSV|Descargar TSV|Descarrega TSV
Download TXT|Descargar TXT|Descarrega TXT
Download ANN|Descargar ANN|Descarrega ANN
Download statistics (.json)|Descargar estadísticas (.json)|Descarrega estadístiques (.json)
Loading your workspace…|Cargando tu espacio de trabajo…|S'està carregant l'espai de treball…
Provisional statistics: annotated documents only|Estadísticas provisionales: solo documentos anotados|Estadístiques provisionals: només documents anotats
Final statistics|Estadísticas finales|Estadístiques finals
Final statistics for annotated documents; failed documents excluded|Estadísticas finales de documentos anotados; se excluyen los fallidos|Estadístiques finals dels documents anotats; s'exclouen els fallits
Corpus entity distribution|Distribución de entidades del corpus|Distribució d'entitats del corpus
Corpus distribution|Distribución del corpus|Distribució del corpus
Find a document|Buscar documento|Cerca un document
Search filename or path|Buscar nombre de archivo o ruta|Cerca per nom de fitxer o ruta
Show documents|Mostrar documentos|Mostra documents
All documents|Todos los documentos|Tots els documents
With annotations|Con anotaciones|Amb anotacions
Without annotations|Sin anotaciones|Sense anotacions
Document state|Estado del documento|Estat del document
All states|Todos los estados|Tots els estats
Sort by name|Ordenar por nombre|Ordena per nom
Previous documents|Documentos anteriores|Documents anteriors
Next documents|Documentos siguientes|Documents següents
Previous document|Documento anterior|Document anterior
Next document|Documento siguiente|Document següent
Original document|Documento original|Document original
Choose a document|Selecciona un documento|Selecciona un document
Find text in this document|Buscar texto en este documento|Cerca text en aquest document
Search original text|Buscar texto original|Cerca text original
Find next|Buscar siguiente|Cerca la següent
← Previous fragment|← Fragmento anterior|← Fragment anterior
Next fragment →|Fragmento siguiente →|Fragment següent →
Entity type filters|Filtros de entidades|Filtres d'entitats
Select highlighted text to inspect every annotation covering that region. Overlap counts indicate multiple mentions.|Selecciona texto resaltado para inspeccionar todas las anotaciones de esa región. Los contadores indican menciones solapadas.|Selecciona text ressaltat per inspeccionar totes les anotacions d'aquella regió. Els comptadors indiquen mencions superposades.
Original annotated document|Documento original anotado|Document original anotat
Annotations in selected region|Anotaciones de la región seleccionada|Anotacions de la regió seleccionada
Open entity details|Abrir detalles de entidad|Obre els detalls de l'entitat
Annotation details|Detalles de la anotación|Detalls de l'anotació
Select a mention in the text or the annotation list.|Selecciona una mención en el texto o en la lista de anotaciones.|Selecciona una menció al text o a la llista d'anotacions.
Annotation table|Tabla de anotaciones|Taula d'anotacions
Entity|Entidad|Entitat
Label|Etiqueta|Etiqueta
Start|Inicio|Inici
End|Fin|Final
Confidence|Confianza|Confiança
Model|Modelo|Model
Mentions in this fragment|Menciones en este fragmento|Mencions en aquest fragment
Find an entity|Buscar entidad|Cerca una entitat
Search mention text|Buscar texto de la mención|Cerca text de la menció
Previous annotation|Anotación anterior|Anotació anterior
Next annotation|Anotación siguiente|Anotació següent
Annotation list|Lista de anotaciones|Llista d'anotacions
Previous 50|50 anteriores|50 anteriors
Next 50|50 siguientes|50 següents
Filter by model|Filtrar por modelo|Filtra per model
All models|Todos los modelos|Tots els models
Results have expired.|Los resultados han caducado.|Els resultats han caducat.
The request could not be loaded.|No se pudo cargar el trabajo.|No s'ha pogut carregar el treball.
Your results have expired. Documents are no longer available.|Tus resultados han caducado. Los documentos ya no están disponibles.|Els resultats han caducat. Els documents ja no estan disponibles.
{count} mentions|{count} menciones|{count} mencions
No annotations|Sin anotaciones|Sense anotacions
No documents|Sin documentos|Sense documents
Select a mention to inspect its original offsets and model.|Selecciona una mención para inspeccionar sus offsets originales y el modelo.|Selecciona una menció per inspeccionar els offsets originals i el model.
Loading document…|Cargando documento…|S'està carregant el document…
Characters {start}–{end} of {total} · original Unicode code-point offsets|Caracteres {start}–{end} de {total} · offsets originales en puntos de código Unicode|Caràcters {start}–{end} de {total} · offsets originals en punts de codi Unicode
Read-only exploration · select a highlighted region or an annotation.|Exploración de solo lectura · selecciona una región resaltada o una anotación.|Exploració de només lectura · selecciona una regió ressaltada o una anotació.
{count} annotation(s) in this region|{count} anotación(es) en esta región|{count} anotació(ns) en aquesta regió
Annotation|Anotación|Anotació
Start / end|Inicio / fin|Inici / final
Original sublabels|Subetiquetas originales|Subetiquetes originals
Model version|Versión del modelo|Versió del model
Overlaps|Solapamientos|Superposicions
Not provided|No disponible|No disponible
Copy entity|Copiar entidad|Copia l'entitat
Copy offsets|Copiar offsets|Copia els offsets
No matches in this document.|No hay coincidencias en este documento.|No hi ha coincidències en aquest document.
Text match at {start}–{end} · {total} match(es) in this document.|Coincidencia en {start}–{end} · {total} coincidencia(s) en el documento.|Coincidència a {start}–{end} · {total} coincidència(es) en el document.
Available until|Disponible hasta|Disponible fins a
after processing finishes|después de finalizar el procesamiento|després de finalitzar el processament
Supporting predictions|Predicciones de soporte|Prediccions de suport
Version|Versión|Versió
Score|Puntuación|Puntuació
Words|Palabras|Paraules
Tokens|Tokens|Tokens
Sentences|Frases|Frases
Entities|Entidades|Entitats
Annotated document progress|Progreso de documentos anotados|Progrés dels documents anotats
Expired|Caducado|Caducat
Results have been deleted or are scheduled for deletion.|Los resultados se han eliminado o está prevista su eliminación.|Els resultats s'han eliminat o se n'ha programat l'eliminació.
72-hour availability begins after processing finishes.|Las 72 horas de disponibilidad comienzan al finalizar el procesamiento.|Les 72 hores de disponibilitat comencen en finalitzar el processament.
Results expire in|Los resultados caducan en|Els resultats caduquen en
Scheduled deletion|Eliminación programada|Eliminació programada
Hide progress|Ocultar progreso|Amaga el progrés
Show progress|Mostrar progreso|Mostra el progrés
Preparing downloads|Preparando descargas|S'estan preparant les descàrregues
Waiting in queue · Position: {count}|En cola · Posición: {count}|A la cua · Posició: {count}
All documents annotated successfully|Todos los documentos se han anotado correctamente|Tots els documents s'han anotat correctament
Completed with document errors · valid partial results available|Completado con errores en documentos · resultados parciales válidos disponibles|Completat amb errors en documents · resultats parcials vàlids disponibles
Processing failed · published documents, if any, are partial results|Procesamiento fallido · los documentos publicados, si existen, son resultados parciales|Processament fallit · els documents publicats, si n'hi ha, són resultats parcials
Processing your documents|Procesando tus documentos|S'estan processant els documents
{done} / {total} annotated · {processing} processing · {pending} pending · {failed} failed|{done} / {total} anotados · {processing} en proceso · {pending} pendientes · {failed} fallidos|{done} / {total} anotats · {processing} en procés · {pending} pendents · {failed} fallits
Document completion, not elapsed-time progress.|Finalización de documentos, no progreso de tiempo transcurrido.|Finalització dels documents, no progrés de temps transcorregut.
Annotations ready|Anotaciones listas|Anotacions preparades
Partial results ready|Resultados parciales listos|Resultats parcials preparats
Processing failed|Procesamiento fallido|Processament fallit
Connection interrupted. Retrying automatically…|Conexión interrumpida. Reintentando automáticamente…|Connexió interrompuda. Es torna a provar automàticament…
Your request is queued.|Tu solicitud está en cola.|La sol·licitud és a la cua.
Your documents are being processed.|Tus documentos se están procesando.|S'estan processant els documents.
Your annotations are ready.|Tus anotaciones están listas.|Les anotacions estan preparades.
Your partial results are ready.|Tus resultados parciales están listos.|Els resultats parcials estan preparats.
Processing failed.|El procesamiento ha fallado.|El processament ha fallat.
Request ID|ID del trabajo|ID del treball
Submitted|Enviado|Enviat
Entity types|Tipos de entidades|Tipus d'entitats
Queue position|Posición en cola|Posició a la cua
Some documents failed. Downloads contain only validated annotated documents and an explicit partial manifest.|Algunos documentos han fallado. Las descargas solo contienen documentos anotados validados y un manifiesto parcial explícito.|Alguns documents han fallat. Les descàrregues només contenen documents anotats validats i un manifest parcial explícit.
Checking your request…|Comprobando tu solicitud…|S'està comprovant la sol·licitud…
Return to this job from your personal workspace.|Vuelve a este trabajo desde tu espacio personal.|Torna a aquest treball des de l'espai personal.
Documentation|Documentación|Documentació
Privacy|Privacidad|Privacitat
Terms of use|Condiciones de uso|Condicions d'ús
Menu|Menú|Menú
Account|Cuenta|Compte
Skip to content|Saltar al contenido|Salta al contingut
Clinical and research use|Uso clínico y de investigación|Ús clínic i de recerca
API reference|Referencia de API|Referència de l'API
Download OpenAPI schema|Descargar esquema OpenAPI|Descarrega l'esquema OpenAPI
Operations|Operaciones|Operacions
Data models|Modelos de datos|Models de dades
Required|Obligatorio|Obligatori
Response codes|Códigos de respuesta|Codis de resposta
PENDING|Pendiente|Pendent
ANNOTATED|Anotado|Anotat
No users match your search.|No hay usuarios que coincidan con la búsqueda.|No hi ha usuaris que coincideixin amb la cerca.
No administrative changes recorded.|No hay cambios administrativos registrados.|No hi ha canvis administratius registrats.
All times are shown in your local timezone.|Las horas se muestran en tu zona horaria local.|Les hores es mostren a la zona horària local.
Request recorded|Solicitud registrada|Sol·licitud registrada
Your jobs are visible only to your account.|Tus trabajos solo son visibles para tu cuenta.|Els teus treballs només són visibles per al teu compte.
Reading mode|Modo de lectura|Mode de lectura
Inline highlights|Resaltados inline|Ressaltats inline
Entity towers|Torres de entidades|Torres d’entitats
Select a label to show its span lines. Select it again to hide them. Smaller mentions appear closest to the text.|Pulsa una etiqueta para mostrar las líneas de su entidad. Púlsala de nuevo para ocultarlas. Las menciones más cortas aparecen más cerca del texto.|Prem una etiqueta per mostrar les línies de la seva entitat. Prem-la de nou per amagar-les. Les mencions més curtes apareixen més a prop del text.
Smaller mentions appear closest to the text. Scroll horizontally to see labels at the edges.|Las menciones más cortas aparecen más cerca del texto. Desplázate horizontalmente para ver las etiquetas de los extremos.|Les mencions més curtes apareixen més a prop del text. Desplaça’t horitzontalment per veure les etiquetes dels extrems.
Offsets use [start, end): end is exclusive.|Los offsets usan [inicio, fin): el final es exclusivo.|Els offsets usen [inici, final): el final és exclusiu.
Research account|Cuenta de investigación|Compte de recerca
Annotations: {count}|Anotaciones: {count}|Anotacions: {count}
Overlapping annotations: {count}. Select a highlight to inspect them.|Anotaciones solapadas: {count}. Selecciona un resaltado para inspeccionarlas.|Anotacions superposades: {count}. Selecciona un ressaltat per inspeccionar-les.
A double underline marks text with multiple annotations. Select a highlight to inspect their exact offsets.|Un subrayado doble indica texto con varias anotaciones. Selecciona un resaltado para inspeccionar sus offsets exactos.|Un subratllat doble indica text amb diverses anotacions. Selecciona un ressaltat per inspeccionar-ne els offsets exactes.
Search|Buscar|Cerca
Email / institution|Email / institución|Correu / institució
Preferred language|Idioma preferido|Llengua preferida
Invalid filename.|Nombre de archivo no válido.|Nom de fitxer no vàlid.
Unsafe or excessively long file path.|La ruta del archivo no es segura o es demasiado larga.|La ruta del fitxer no és segura o és massa llarga.
Unsupported file path.|Ruta de archivo no admitida.|Ruta de fitxer no admesa.
The upload exceeds the configured limit.|La subida supera el límite configurado.|La pujada supera el límit configurat.
Upload exceeds the configured limit.|La subida supera el límite configurado.|La pujada supera el límit configurat.
No text documents were found.|No se han encontrado documentos de texto.|No s'han trobat documents de text.
Conflicting file and directory paths.|Hay rutas de archivos y carpetas en conflicto.|Hi ha rutes de fitxers i carpetes en conflicte.
Only .txt documents or a single ZIP are allowed.|Solo se admiten documentos .txt o un único ZIP.|Només s'admeten documents .txt o un únic ZIP.
Duplicate document paths are not allowed.|No se admiten rutas de documentos duplicadas.|No s'admeten rutes de documents duplicades.
A request may contain at most {count} documents.|Una solicitud puede contener como máximo {count} documentos.|Una sol·licitud pot contenir com a màxim {count} documents.
Documents exceed the uncompressed size limit.|Los documentos superan el límite de tamaño descomprimido.|Els documents superen el límit de mida descomprimida.
Empty documents are not supported.|No se admiten documentos vacíos.|No s'admeten documents buits.
Binary content is not allowed in text documents.|No se admite contenido binario en documentos de texto.|No s'admet contingut binari en documents de text.
All documents must be UTF-8 text.|Todos los documentos deben ser texto UTF-8.|Tots els documents han de ser text UTF-8.
The ZIP file is corrupt or uses an unsupported format.|El archivo ZIP está dañado o utiliza un formato no admitido.|El fitxer ZIP està malmès o utilitza un format no admès.
Too many ZIP entries.|El ZIP contiene demasiadas entradas.|El ZIP conté massa entrades.
ZIP uncompressed size exceeds the limit.|El tamaño descomprimido del ZIP supera el límite.|La mida descomprimida del ZIP supera el límit.
Duplicate ZIP paths are not allowed.|No se admiten rutas duplicadas en el ZIP.|No s'admeten rutes duplicades al ZIP.
Links, special or encrypted files are not supported.|No se admiten enlaces ni archivos especiales o cifrados.|No s'admeten enllaços ni fitxers especials o xifrats.
ZIP compression ratio or document size exceeds the limit.|La relación de compresión del ZIP o el tamaño de un documento supera el límite.|La relació de compressió del ZIP o la mida d'un document supera el límit.
ZIP may contain only TXT files and folders; nested ZIPs are not supported.|El ZIP solo puede contener archivos TXT y carpetas; no se admiten ZIP anidados.|El ZIP només pot contenir fitxers TXT i carpetes; no s'admeten ZIP imbricats.
Choose a language and one or more available models.|Elige un idioma y uno o varios modelos disponibles.|Tria una llengua i un o diversos models disponibles.
Choose distinct available checkpoints.|Elige modelos disponibles diferentes.|Tria models disponibles diferents.
Entity categories do not match the selected checkpoints.|Las categorías de entidades no coinciden con los modelos seleccionados.|Les categories d'entitats no coincideixen amb els models seleccionats.
Choose one or more available models.|Elige uno o varios modelos disponibles.|Tria un o diversos models disponibles.
A checkpoint is unavailable for this language.|Un modelo no está disponible para este idioma.|Un model no està disponible per a aquesta llengua.
Unknown checkpoint selection.|Selección de modelos desconocida.|Selecció de models desconeguda.
Choose checkpoints explicitly for categories with multiple models.|Selecciona explícitamente los modelos en categorías con varias opciones.|Selecciona explícitament els models a les categories amb diverses opcions.
Choose exactly one input mode.|Elige un único modo de entrada.|Tria un únic mode d'entrada.
Enter your name, a valid email, language and entity types.|Introduce el nombre, un email válido, el idioma y los tipos de entidades.|Introdueix el nom, un correu vàlid, la llengua i els tipus d'entitats.
Paste text without files.|Pega texto sin adjuntar archivos.|Enganxa text sense adjuntar fitxers.
Unknown input mode.|Modo de entrada desconocido.|Mode d'entrada desconegut.
Select TXT files or one ZIP, without pasted text.|Selecciona archivos TXT o un ZIP, sin texto pegado.|Selecciona fitxers TXT o un ZIP, sense text enganxat.
Storage capacity is temporarily unavailable.|El almacenamiento no está disponible temporalmente.|L'emmagatzematge no està disponible temporalment.
Request not found.|No se ha encontrado el trabajo.|No s'ha trobat el treball.
The service is busy. Please try again shortly.|El servicio está ocupado. Inténtalo en unos instantes.|El servei està ocupat. Torna-ho a provar d'aquí a uns instants.
Upload lease expired; retry your submission.|La reserva de subida ha caducado; vuelve a enviar la solicitud.|La reserva de pujada ha caducat; torna a enviar la sol·licitud.
The queue is full. Please try again later.|La cola está llena. Inténtalo más tarde.|La cua és plena. Torna-ho a provar més tard.
You can submit one request per minute. Please try again shortly.|Puedes enviar una solicitud por minuto. Inténtalo en unos instantes.|Pots enviar una sol·licitud per minut. Torna-ho a provar d'aquí a uns instants.
Check your name, email, language, entities and files.|Revisa el nombre, el email, el idioma, las entidades y los archivos.|Revisa el nom, el correu, la llengua, les entitats i els fitxers.
No validated local checkpoint.|No hay un modelo local validado.|No hi ha cap model local validat.
No published, validated checkpoint registered.|No hay un modelo publicado y validado registrado.|No hi ha cap model publicat i validat registrat.
Disease mentions|Menciones de enfermedades|Mencions de malalties
Checkpoint not installed; original label schema and native compatibility require offline validation.|Modelo no instalado; el esquema original de etiquetas y la compatibilidad nativa requieren validación sin conexión.|Model no instal·lat; l'esquema original d'etiquetes i la compatibilitat nativa requereixen validació fora de línia.
No published, validated checkpoint; pediatric experiment only.|No hay un modelo publicado y validado; solo es un experimento pediátrico.|No hi ha cap model publicat i validat; només és un experiment pediàtric.
Subcategorization model registered. Verify input contract/pre-tokenization and whether upstream spans are required; no standalone execution until reviewed.|Modelo de subcategorización registrado. Hay que verificar el contrato de entrada, la pretokenización y si requiere spans previos; no se ejecuta de forma independiente hasta su revisión.|Model de subcategorització registrat. Cal verificar el contracte d'entrada, la pretokenització i si requereix spans previs; no s'executa de manera independent fins a la revisió.
Workbook marks this checkpoint as not released.|El inventario indica que este modelo no se ha publicado.|L'inventari indica que aquest model no s'ha publicat.
Available|Disponible|Disponible
Cached · ready to load|En caché · listo para cargar|En memòria cau · a punt per carregar
Download on first use|Descarga en el primer uso|Descàrrega en el primer ús
Preparing models · downloading uncached checkpoints|Preparando modelos · descargando los que faltan en caché|Preparant models · descarregant els que falten a la memòria cau
Completed with errors · valid partial results available|Finalizado con incidencias · resultados parciales válidos disponibles|Finalitzat amb incidències · resultats parcials vàlids disponibles
No configured models are available for this language.|No hay modelos configurados disponibles para este idioma.|No hi ha models configurats disponibles per a aquesta llengua.
No model repository or local directory configured.|No hay un repositorio ni un directorio local configurado para el modelo.|No hi ha cap repositori ni directori local configurat per al model.
Unavailable|No disponible|No disponible
Lane|Carril|Carril
Offsets|Offsets|Offsets
{count} annotation(s)|{count} anotación(es)|{count} anotació(ns)
NLP4BIA API|API de NLP4BIA|API de NLP4BIA
Submit corpora, follow private jobs and explore original-coordinate annotations.|Envía corpus, sigue tus trabajos privados y explora anotaciones en coordenadas originales.|Envia corpus, segueix els treballs privats i explora anotacions en coordenades originals.
The form requires JavaScript. The REST API remains available.|El formulario necesita JavaScript. La API REST sigue disponible.|El formulari necessita JavaScript. L'API REST continua disponible.
Diseases|Enfermedades|Malalties
Symptoms|Síntomas|Símptomes
Medications|Medicamentos|Medicaments
Procedures|Procedimientos|Procediments
Anonymization|Anonimización|Anonimització
Events|Eventos|Esdeveniments
Human|Personas|Persones
Locations|Localizaciones|Localitzacions
Negation / Uncertainty|Negación / Incertidumbre|Negació / Incertesa
Professions|Profesiones|Professions
Situations|Situaciones|Situacions
Species|Especies|Espècies
Temporality|Temporalidad|Temporalitat
English|Inglés|Anglès
Spanish|Español|Espanyol
Catalan|Catalán|Català
Czech|Checo|Txec
Dutch|Neerlandés|Neerlandès
Greek|Griego|Grec
Italian|Italiano|Italià
Romanian|Rumano|Romanès
Swedish|Sueco|Suec
Multilingual checkpoints are validated per document language. Check availability before submitting.|Los modelos multilingües se validan por idioma del documento. Comprueba la disponibilidad antes de enviar.|Els models multilingües es validen per llengua del document. Comprova la disponibilitat abans d'enviar.
"""

_COPY += """
All uploads|Todas las subidas|Totes les pujades
Concept normalization|Normalización de conceptos|Normalització de conceptes
De-identification responsibility|Responsabilidad de desidentificación|Responsabilitat de desidentificació
Delete|Eliminar|Elimina
Delete document|Eliminar documento|Elimina el document
Delete retained documents at any time. Upload history remains after content deletion.|Elimina documentos conservados en cualquier momento. El histórico de subidas permanece tras borrarlos.|Elimina documents conservats en qualsevol moment. L'historial de pujades es conserva després d'esborrar-los.
Deleted documents|Documentos eliminados|Documents eliminats
Deleting…|Eliminando…|S'està eliminant…
Document content deleted. Upload history retained.|Contenido del documento eliminado. Histórico de subidas conservado.|Contingut del document eliminat. Historial de pujades conservat.
Document usage|Uso de documentos|Ús de documents
English fallback: original mention, without automatic translation.|Alternativa en inglés: mención original, sin traducción automática.|Alternativa en anglès: menció original, sense traducció automàtica.
Expired documents|Documentos caducados|Documents caducats
History keeps upload metadata, never deleted document content.|El histórico conserva los metadatos de subida, nunca el contenido eliminado.|L'historial conserva les metadades de pujada, mai el contingut eliminat.
Manage documents|Gestionar documentos|Gestiona els documents
My documents|Mis documentos|Els meus documents
New accounts can retain 100 documents across all jobs. Delete documents to free slots. Higher limits may be granted by the NLP4BIA team.|Las cuentas nuevas pueden conservar 100 documentos entre todos sus trabajos. Elimina documentos para liberar plazas. El equipo NLP4BIA puede ampliar el límite.|Els comptes nous poden conservar 100 documents entre tots els treballs. Elimina documents per alliberar places. L'equip NLP4BIA pot ampliar el límit.
No document quota limit|Sin límite de cuota de documentos|Sense límit de quota de documents
Normalize medications, procedures, diseases and symptoms using the terminology installed by the administrator. Missing resources leave NER results available.|Normaliza medicamentos, procedimientos, enfermedades y síntomas con la terminología instalada por el administrador. Si faltan recursos, los resultados NER siguen disponibles.|Normalitza medicaments, procediments, malalties i símptomes amb la terminologia instal·lada per l'administrador. Si falten recursos, els resultats NER continuen disponibles.
Refresh|Actualizar|Actualitza
Retained documents|Documentos conservados|Documents conservats
Show|Mostrar|Mostra
Similarity|Similitud|Similitud
This removes the original document, its annotations and downloads. Upload history remains.|Se eliminarán el documento original, sus anotaciones y descargas. El histórico de subidas permanece.|S'eliminaran el document original, les anotacions i les descàrregues. L'historial de pujades es conserva.
Total documents uploaded: {count}|Total de documentos subidos: {count}|Total de documents pujats: {count}
You are responsible for de-identifying documents before upload. The platform and its maintainers accept no responsibility for documents uploaded with identifying information.|Eres responsable de desidentificar los documentos antes de subirlos. La plataforma y sus responsables no se hacen responsables de los documentos subidos con información identificativa.|Ets responsable de desidentificar els documents abans de pujar-los. La plataforma i els seus responsables no es fan responsables dels documents pujats amb informació identificativa.
occupied / limit|ocupados / límite|ocupats / límit
{count} document slots available|{count} plazas de documentos disponibles|{count} places de documents disponibles
STORED|Conservado|Conservat
DELETED|Eliminado|Eliminat
NORMALIZATION|Normalización de conceptos|Normalització de conceptes
"""

_COPY += "Your retained-document limit has been reached. Delete documents to free space.|Has alcanzado el límite de documentos conservados. Elimina documentos para liberar espacio.|Has arribat al límit de documents conservats. Elimina documents per alliberar espai.\n"

ROWS = {
    row.split("|")[0]: tuple(row.split("|")) for row in _COPY.strip().splitlines() if row.strip()
}

_BASE_MESSAGES = {**AUTH_ROWS, **{v[0]: v for v in AUTH_ROWS.values()}, **ROWS}
MESSAGES = {
    key: tuple(
        row[("en", "es", "ca").index(code)]
        if code in ("en", "es", "ca")
        else translated(row[0], code)
        for code in CODES
    )
    for key, row in _BASE_MESSAGES.items()
}


def translate(key, language="en", **values):
    column = CODES.index(language) if language in CODES else 0
    value = MESSAGES[key][column] if key in MESSAGES else key
    return value.format(**values) if values else value
