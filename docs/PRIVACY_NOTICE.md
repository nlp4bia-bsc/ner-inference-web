# Privacy notice — draft for institutional review

**Not a final or institutionally approved legal notice.** NLP4BIA / Barcelona
Supercomputing Center must review and supply the responsible entity, lawful basis,
applicable jurisdiction, privacy contact and rights procedure before production.
No contact address or compliance certification is asserted here.

The application stores account name, normalized email, institution, professional
activity, preferred language, legal acknowledgment and security state. It stores
Argon2id password hashes, session/action-token verifiers and audited security/account
actions. Optional SMTP delivers verification/recovery links; passwords are never sent.
New access requests store approval state and await an administrator review; existing
accounts are grandfathered as approved. Email verification is disabled by default.
Local mailbox capture is prohibited in production. Authentication abuse counters
use keyed identifiers; the sessions interface does not expose IPs or token hashes.

Uploaded/pasted text, source paths, model selections, annotations, exports and job
metadata are associated with their uploading account. Owners and authorized
MFA-authenticated administrators can inspect documents, annotations and exports.
Administrators review access requests, see profile details, adjust quotas, and
can delete any project or account with its owned data. Submit only data you
are authorized to process under the applicable institutional research policy.

Job files/results expire 72 hours after terminal completion, including failed/partial
jobs, and become inaccessible at the deadline. Physical removal is asynchronous.
Job tombstones expire later according to the configured policy. Account records are
persistent until administrator deletion; audit retention defaults to 365 days.
Backups, logs and any downstream copies require a separate institutional policy.
See [RETENTION_POLICY.md](RETENTION_POLICY.md) for implementation and limits.

The interface uses essential HttpOnly session, CSRF-challenge and language cookies.
It does not store credentials or clinical text in localStorage/sessionStorage, load
external fonts or add analytics/tracking services. External footer/repository/model
links lead to their respective sites when selected; local clinical text is not
included in those link URLs.

Authenticated users can request account deletion from Profile. This records an
audited request for institutional review; it is not automatic deletion and does
not alter result expiry. Administrators can execute account deletion, revoking
sessions and removing the profile, owned projects, token records and upload history.
Opaque audit identifiers remain under audit retention. Failed erasure remains
blocked and can be retried; file unlinking does not erase backups or downloaded copies.
The institution must define identity verification,
retention obligations and how requests are handled before opening the service.

## Español — borrador para revisión institucional

Este texto no es un aviso legal definitivo ni aprobado. La institución debe definir
responsable, base jurídica, jurisdicción, contacto y procedimiento de derechos.
Se guardan datos de cuenta, verificadores de seguridad y registros de auditoría;
los documentos y resultados son accesibles por su propietario y administradores
autorizados con MFA. Las nuevas solicitudes requieren aprobación administrativa.
El administrador puede modificar cuotas y eliminar cuentas con sus proyectos.
Los archivos caducan 72 horas después de finalizar el trabajo; las cuentas y copias
de seguridad tienen políticas distintas. Se usan cookies esenciales, sin analítica
ni fuentes externas. La solicitud de eliminación del perfil queda registrada para
revisión institucional y no equivale a eliminación inmediata. Consulta el texto
principal y la política de retención para el alcance técnico.

## Català — esborrany per a revisió institucional

Aquest text no és un avís legal definitiu ni aprovat. La institució ha de definir
responsable, base jurídica, jurisdicció, contacte i procediment de drets. Es desen
dades del compte, verificadors de seguretat i registres d'auditoria; els documents
i resultats són accessibles pel propietari i administradors autoritzats amb MFA.
Les noves sol·licituds requereixen aprovació administrativa. L’administrador pot
modificar quotes i eliminar comptes amb els seus projectes. Els fitxers caduquen
72 hores després de finalitzar el treball; els comptes i les còpies de seguretat
tenen polítiques diferents. S'utilitzen galetes essencials, sense analítica ni fonts
externes. La sol·licitud d'eliminació del perfil queda registrada per a revisió
institucional i no equival a eliminació immediata. Consulta el text principal i la
política de retenció per a l'abast tècnic.
