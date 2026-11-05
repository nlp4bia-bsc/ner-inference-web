# Privacy notice — draft for institutional review

**Not a final or institutionally approved legal notice.** NLP4BIA / Barcelona
Supercomputing Center must review and supply the responsible entity, lawful basis,
applicable jurisdiction, privacy contact and rights procedure before production.
No contact address or compliance certification is asserted here.

The application stores account name, normalized email, institution, professional
activity, preferred language, legal acknowledgment and security state. It stores
Argon2id password hashes, session/action-token verifiers and audited security/account
actions. SMTP verifies email and delivers recovery links; passwords are never sent.
Local mailbox capture is prohibited in production. Authentication abuse counters
use keyed identifiers; the sessions interface does not expose IPs or token hashes.

Uploaded/pasted text, source paths, model selections, annotations, exports and job
metadata belong to the authenticated account. Administrators manage permissions
without automatic access to other owners' clinical documents. Submit only data you
are authorized to process under the applicable institutional research policy.

Job files/results expire 72 hours after terminal completion, including failed/partial
jobs, and become inaccessible at the deadline. Physical removal is asynchronous.
Job tombstones expire later according to the configured policy. Account records are
persistent until institutionally managed; audit retention defaults to 365 days.
Backups, logs and any downstream copies require a separate institutional policy.
See [RETENTION_POLICY.md](RETENTION_POLICY.md) for implementation and limits.

The interface uses essential HttpOnly session, CSRF-challenge and language cookies.
It does not store credentials or clinical text in localStorage/sessionStorage, load
external fonts or add analytics/tracking services. External footer/repository/model
links lead to their respective sites when selected; local clinical text is not
included in those link URLs.

Authenticated users can request account deletion from Profile. This records an
audited request for institutional review; it is not automatic deletion and does
not alter result expiry. The institution must define identity verification,
retention obligations and how requests are handled before opening the service.

## Español — borrador para revisión institucional

Este texto no es un aviso legal definitivo ni aprobado. La institución debe definir
responsable, base jurídica, jurisdicción, contacto y procedimiento de derechos.
Se guardan datos de cuenta, verificadores de seguridad y registros de auditoría;
los documentos y resultados solo son accesibles por su propietario autenticado.
Los archivos caducan 72 horas después de finalizar el trabajo; las cuentas y copias
de seguridad tienen políticas distintas. Se usan cookies esenciales, sin analítica
ni fuentes externas. La solicitud de eliminación del perfil queda registrada para
revisión institucional y no equivale a eliminación inmediata. Consulta el texto
principal y la política de retención para el alcance técnico.

## Català — esborrany per a revisió institucional

Aquest text no és un avís legal definitiu ni aprovat. La institució ha de definir
responsable, base jurídica, jurisdicció, contacte i procediment de drets. Es desen
dades del compte, verificadors de seguretat i registres d'auditoria; els documents
i resultats només són accessibles pel propietari autenticat. Els fitxers caduquen
72 hores després de finalitzar el treball; els comptes i les còpies de seguretat
tenen polítiques diferents. S'utilitzen galetes essencials, sense analítica ni fonts
externes. La sol·licitud d'eliminació del perfil queda registrada per a revisió
institucional i no equival a eliminació immediata. Consulta el text principal i la
política de retenció per a l'abast tècnic.
