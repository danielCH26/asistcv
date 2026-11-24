/**
 * Contenido legal de la Plataforma (Términos, Privacidad, Cookies).
 *
 * Vive fuera de los JSON de i18n a propósito: son documentos largos con
 * estructura (secciones, párrafos, viñetas) y su propio ciclo de versiones.
 * Los JSON se quedan con las etiquetas cortas de la UI; acá va el texto de
 * cada documento en los dos idiomas soportados (es/en), y las páginas
 * `/terms`, `/privacy` y `/cookies` eligen según el locale activo con
 * fallback a español (Colombia es el mercado primario).
 *
 * Marco de referencia del contenido:
 * - Ley 1581 de 2012 y Decreto 1377 de 2013 (datos personales, Colombia).
 * - Ley 1480 de 2011 (Estatuto del Consumidor: retracto, art. 47).
 * - Ley 527 de 1999 (comercio electrónico, mensajes de datos).
 *
 * Identificación del titular (datos del operador, nov 2026): «eptus» es
 * operado como persona natural por Daniel Elias Cordoba Howard, C.C.
 * 1123890948, contacto eptus.asistcv@gmail.com. Cuando exista sociedad
 * registrada (NIT), actualizar la identificación en los dos idiomas y
 * subir la versión de los documentos.
 *
 * Este contenido es una base redactada para
 * el producto real (planes COP, pasarelas Wompi/Mercado Pago, retención de
 * auditorías a 30 días, etc. según los modelos de `app/db/models.py` y el
 * catálogo de `app/api/v1/billing.py`) y NO sustituye revisión jurídica.
 */

export type LegalDocKind = 'terms' | 'privacy' | 'cookies';

/** Bloque con encabezado propio dentro de una sección (h3). */
export interface LegalBlock {
	title: string;
	paragraphs?: string[];
	bullets?: string[];
}

/** Sección numerada del documento (h2). */
export interface LegalSection {
	id: string;
	title: string;
	paragraphs?: string[];
	bullets?: string[];
	blocks?: LegalBlock[];
}

export interface LegalDoc {
	version: string;
	/** Línea de metadatos ya redactada en el idioma del documento. */
	meta: string;
	title: string;
	intro: string[];
	sections: LegalSection[];
}

const UPDATED_DATE_ES = '24 de noviembre de 2026';
const UPDATED_DATE_EN = 'November 24, 2026';

// =====================================================================
// TÉRMINOS Y CONDICIONES
// =====================================================================

const termsEs: LegalDoc = {
	version: '1.0',
	meta: `Versión 1.0 · Última actualización: ${UPDATED_DATE_ES}`,
	title: 'Términos y Condiciones',
	intro: [
		'Los presentes Términos y Condiciones («Términos») regulan el acceso y el uso de AsistCV, la plataforma de análisis y adaptación de hojas de vida operada por Daniel Elias Cordoba Howard bajo la marca «eptus» («eptus», «nosotros»).',
		'Al crear una cuenta, adquirir un plan o utilizar cualquier función de la Plataforma, usted («Usuario») declara que ha leído y acepta estos Términos y nuestra Política de Privacidad. Si no está de acuerdo, no utilice la Plataforma.'
	],
	sections: [
		{
			id: 'titular',
			title: 'Información del titular',
			bullets: [
				'Titular y operador: Daniel Elias Cordoba Howard, mayor de edad, identificado con cédula de ciudadanía No. 1123890948, quien opera la Plataforma bajo la marca «eptus» (persona natural; a la fecha no existe sociedad registrada).',
				'Contacto: eptus.asistcv@gmail.com.',
				'La Plataforma se presta a través de su sitio web y su aplicación web, apoyados en los proveedores de infraestructura descritos en la Política de Privacidad.'
			]
		},
		{
			id: 'servicio',
			title: 'Objeto y naturaleza del servicio',
			paragraphs: [
				'AsistCV le ayuda a decidir dónde invertir su energía en la búsqueda de empleo y a preparar su hoja de vida para las vacantes que valen la pena. En concreto, la Plataforma ofrece:'
			],
			bullets: [
				'Un análisis de compatibilidad («match») entre su hoja de vida y la descripción de una vacante, con puntaje, razones, brechas de habilidades y una recomendación de cuánta energía invertir.',
				'La adaptación de las viñetas de su hoja de vida contra la descripción de la vacante. Un validador anti-invención rechaza cualquier habilidad o logro que no esté presente en su hoja de vida original, y toda adaptación requiere su aprobación antes de que la use.',
				'Una auditoría de hoja de vida sin registro, con límites de uso diario.',
				'Alertas de ofertas de empleo según sus preferencias y su plan.'
			],
			blocks: [
				{
					title: 'Naturaleza asistiva',
					paragraphs: [
						'La Plataforma es una herramienta de apoyo a la decisión. Los resultados son orientativos, no garantizan contratación, entrevistas ni resultados laborales. La Plataforma no postula automáticamente a vacantes ni envía aplicaciones sin su acción; las decisiones de contratación corresponden exclusivamente a terceros.'
					]
				}
			]
		},
		{
			id: 'cuenta',
			title: 'Registro y cuenta',
			bullets: [
				'El servicio está dirigido a personas mayores de 18 años, con capacidad legal para obligarse.',
				'El acceso se realiza con su correo electrónico y un código de verificación. Usted es responsable de la exactitud de los datos que registra, de la seguridad de su buzón de correo y de mantener el control de su cuenta.',
				'Debe avisarnos de inmediato a eptus.asistcv@gmail.com si detecta un acceso no autorizado a su cuenta.',
				'Si usted es reclutador, su rol está sujeto a la verificación que hagamos de la cuenta, y garantiza contar con la autorización de los candidatos cuyas hojas de vida cargue.'
			]
		},
		{
			id: 'uso-aceptable',
			title: 'Uso aceptable',
			paragraphs: [
				'Al usar la Plataforma usted se compromete a no:'
			],
			bullets: [
				'Usarla para fines ilícitos o para discriminar candidatos por razones protegidas por la ley.',
				'Cargar hojas de vida de terceros sin su autorización expresa.',
				'Evadir los límites de su plan mediante cuentas múltiples, automatización abusiva o reventa del acceso.',
				'Intentar vulnerar las medidas de seguridad (límites de tasa, control de acceso, aislamiento de datos) o hacer extracciones masivas de contenido («scraping»).',
				'Reproducir, aplicar ingeniería inversa o crear obras derivadas de la Plataforma, salvo lo expresamente permitido por la ley.',
				'Cargar contenido malicioso o que vulnere derechos de terceros.'
			]
		},
		{
			id: 'contenido-usuario',
			title: 'Su contenido',
			paragraphs: [
				'Su hoja de vida, las vacantes que pega y las adaptaciones que aprueba son suyos. No le quitamos la titularidad de nada de eso.',
				'Para operar el servicio usted nos concede una licencia limitada, no exclusiva y revocable, sin regalías, para procesar ese contenido dentro de la Plataforma: generar representaciones numéricas (embeddings), calcular el match, producir y guardar adaptaciones y mantener su historial.',
				'No vendemos su información ni la usamos para publicidad. Los detalles de tratamiento, los proveedores involucrados y los plazos de conservación están en la Política de Privacidad.'
			]
		},
		{
			id: 'planes-pagos',
			title: 'Planes, precios y pagos',
			paragraphs: [
				'Los precios están expresados en pesos colombianos (COP) y los publica la sección Planes de la Plataforma. El catálogo vigente al momento del pago es el que aplica a su compra. Como referencia, el catálogo actual es:'
			],
			bullets: [
				'Plan gratuito: 3 matches al mes y 1 análisis de hoja de vida. No requiere tarjeta.',
				'Job Seeker Monthly: 29.000 COP/mes — 50 matches y 10 adaptaciones al mes.',
				'Recruiter Starter: 99.000 COP/mes.',
				'Recruiter Business: 199.000 COP/mes.',
				'Recruiter Agency: 499.000 COP/mes.'
			],
			blocks: [
				{
					title: 'Pagos',
					paragraphs: [
						'Los pagos se procesan a través de pasarelas habilitadas (actualmente Wompi y Mercado Pago). eptus no recibe ni almacena números de tarjeta: el cobro lo realiza la pasarela con sus propios términos, seguridad y soporte, que también le aplican al usarla.',
						'Los límites de cada plan se renuevan cada mes calendario y no se acumulan para el período siguiente.'
					]
				}
			]
		},
		{
			id: 'cancelacion-reembolsos',
			title: 'Renovación, cancelación y reembolsos',
			bullets: [
				'El plan pagado cubre un período mensual contado desde la confirmación del pago. Puede consultar el estado de su plan en la página Plan de su cuenta.',
				'Puede cancelar en cualquier momento desde la página Plan: conserva el acceso hasta el final del período ya pagado y después pasa al plan gratuito. Su hoja de vida y su historial se conservan.',
				'Retracto y reembolsos: conforme al Estatuto del Consumidor (Ley 1480 de 2011, artículo 47), puede ejercer el derecho de retracto dentro de los cinco (5) días hábiles siguientes a la compra, salvo que el servicio haya comenzado a ejecutarse con su acuerdo. En la práctica: escribimos el reembolso total si nos contacta a eptus.asistcv@gmail.com dentro de ese plazo y no ha consumido los beneficios pagos de su plan. Si ya consumió beneficios del plan, el retracto no procede por tratarse de un servicio ya ejecutado.',
				'Los cobros duplicados o erróneos se reembolsan o corrigen por el mismo medio de pago en un máximo de treinta (30) días calendario.'
			]
		},
		{
			id: 'propiedad-intelectual',
			title: 'Propiedad intelectual',
			paragraphs: [
				'La Plataforma, su software, su diseño, sus textos y las marcas eptus y AsistCV pertenecen a su titular y operador. Le concedemos una licencia de uso personal, limitada, no transferible y revocable, exclusivamente para usar el servicio conforme a estos Términos.',
				'Sus hojas de vida, vacantes y adaptaciones aprobadas son suyos y usted decide cómo usarlos.',
				'Si nos comparte comentarios o sugerencias, nos autoriza a usarlos para mejorar el producto, sin obligación de compensación.'
			]
		},
		{
			id: 'ia-resultados',
			title: 'Naturaleza de los resultados e inteligencia artificial',
			bullets: [
				'Los análisis y adaptaciones se generan con sistemas de inteligencia artificial y pueden contener errores u omisiones: son una recomendación orientativa, no una verdad definitiva.',
				'El validador anti-invención reduce el riesgo de que una adaptación invente experiencia, pero no lo elimina por completo. Revise y apruebe siempre el contenido antes de usarlo.',
				'No garantizamos resultados laborales, entrevistas ni contrataciones.'
			]
		},
		{
			id: 'disponibilidad',
			title: 'Disponibilidad, soporte y suspensiones',
			bullets: [
				'La Plataforma se ofrece «tal cual», con esfuerzo razonable de disponibilidad. Pueden presentarse interrupciones por mantenimiento o por dependencias de terceros.',
				'El soporte se presta por eptus.asistcv@gmail.com.',
				'Podemos suspender o deshabilitar cuentas que incumplan estos Términos, con aviso previo cuando sea posible.',
				'Usted puede terminar su cuenta en cualquier momento; el tratamiento posterior de sus datos se rige por la Política de Privacidad.'
			]
		},
		{
			id: 'responsabilidad',
			title: 'Limitación de responsabilidad',
			paragraphs: [
				'En la máxima medida permitida por la ley colombiana, eptus no responde por daños indirectos, incidentales, lucro cesante o pérdida de información fuera de su control razonable.',
				'La responsabilidad total de eptus frente a cualquier reclamación se limita al monto que usted haya pagado efectivamente por la Plataforma en los tres (3) meses anteriores al hecho que genera la responsabilidad.'
			]
		},
		{
			id: 'cambios',
			title: 'Cambios a estos Términos',
			paragraphs: [
				'Publicamos nuevas versiones en esta página, con número de versión y fecha. Los cambios sustanciales se avisan con al menos quince (15) días de antelación dentro de la Plataforma o al correo registrado.',
				'Si sigue usando la Plataforma después de entrar en vigencia una nueva versión, se entiende que la acepta. Si no está de acuerdo, deje de usar la Plataforma y cancele su plan.'
			]
		},
		{
			id: 'ley-aplicable',
			title: 'Ley aplicable y solución de controversias',
			bullets: [
				'Estos Términos se rigen por las leyes de la República de Colombia.',
				'Como consumidor, usted cuenta con las garantías del Estatuto del Consumidor y puede acudir a la Superintendencia de Industria y Comercio.',
				'Cualquier controversia se intentará resolver primero de manera amistosa, dentro de los treinta (30) días siguientes a la notificación. De no lograrse, será competente la jurisdicción colombiana del domicilio del titular.'
			]
		},
		{
			id: 'contacto',
			title: 'Contacto',
			paragraphs: [
				'Preguntas, soporte y reclamaciones: eptus.asistcv@gmail.com.'
			]
		}
	]
};

const termsEn: LegalDoc = {
	version: '1.0',
	meta: `Version 1.0 · Last updated: ${UPDATED_DATE_EN}`,
	title: 'Terms and Conditions',
	intro: [
		'These Terms and Conditions («Terms») govern access to and use of AsistCV, the résumé analysis and adaptation platform operated by Daniel Elias Cordoba Howard under the «eptus» brand («eptus», «we»).',
		'By creating an account, purchasing a plan or using any feature of the Platform, you («User») declare that you have read and accept these Terms and our Privacy Policy. If you do not agree, do not use the Platform.'
	],
	sections: [
		{
			id: 'titular',
			title: 'Operator information',
			bullets: [
				'Owner and operator: Daniel Elias Cordoba Howard, of legal age, identified with Colombian citizenship card (cédula de ciudadanía) No. 1123890948, operating the Platform under the «eptus» brand (natural person; no registered company yet).',
				'Contact: eptus.asistcv@gmail.com.',
				'The Platform is provided through its website and web application, supported by the infrastructure providers described in the Privacy Policy.'
			]
		},
		{
			id: 'servicio',
			title: 'Purpose and nature of the service',
			paragraphs: [
				'AsistCV helps you decide where to invest your energy in a job search and prepare your résumé for the openings that are worth it. Specifically, the Platform offers:'
			],
			bullets: [
				'A compatibility analysis («match») between your résumé and a job description, with a score, reasons, skill gaps and a recommendation of how much energy to invest.',
				'Adaptation of your résumé bullet points against the job description. An anti-hallucination validator rejects any skill or achievement not present in your original résumé, and every adaptation requires your approval before you use it.',
				'A résumé audit without registration, subject to daily usage limits.',
				'Job alerts according to your preferences and plan.'
			],
			blocks: [
				{
					title: 'Assistive nature',
					paragraphs: [
						'The Platform is a decision-support tool. Results are indicative and do not guarantee hiring, interviews or job outcomes. The Platform does not auto-apply to jobs or send applications without your action; hiring decisions belong exclusively to third parties.'
					]
				}
			]
		},
		{
			id: 'cuenta',
			title: 'Registration and account',
			bullets: [
				'The service is intended for individuals aged 18 or older with legal capacity.',
				'Access works with your email address and a verification code. You are responsible for the accuracy of the information you provide, for the security of your mailbox and for keeping control of your account.',
				'You must notify us immediately at eptus.asistcv@gmail.com if you detect unauthorized access to your account.',
				'If you are a recruiter, your role is subject to account verification, and you warrant that you have the authorization of the candidates whose résumés you upload.'
			]
		},
		{
			id: 'uso-aceptable',
			title: 'Acceptable use',
			paragraphs: ['By using the Platform you agree not to:'],
			bullets: [
				'Use it for unlawful purposes or to discriminate against candidates for legally protected reasons.',
				'Upload third-party résumés without their express authorization.',
				'Circumvent your plan limits through multiple accounts, abusive automation or reselling access.',
				'Attempt to breach security measures (rate limits, access control, data isolation) or perform bulk content extraction («scraping»).',
				'Reverse engineer, decompile or create derivative works of the Platform, except as expressly permitted by law.',
				'Upload malicious content or content that infringes third-party rights.'
			]
		},
		{
			id: 'contenido-usuario',
			title: 'Your content',
			paragraphs: [
				'Your résumé, the job descriptions you paste and the adaptations you approve are yours. We do not take ownership of any of it.',
				'To operate the service, you grant us a limited, non-exclusive, revocable, royalty-free license to process that content within the Platform: generate numerical representations (embeddings), compute the match, produce and store adaptations and maintain your history.',
				'We do not sell your information or use it for advertising. Processing details, providers and retention periods are described in the Privacy Policy.'
			]
		},
		{
			id: 'planes-pagos',
			title: 'Plans, prices and payments',
			paragraphs: [
				'Prices are expressed in Colombian pesos (COP) and published in the Plans section of the Platform. The catalog in effect at the time of payment applies to your purchase. For reference, the current catalog is:'
			],
			bullets: [
				'Free plan: 3 matches per month and 1 résumé analysis. No card required.',
				'Job Seeker Monthly: 29,000 COP/month — 50 matches and 10 adaptations per month.',
				'Recruiter Starter: 99,000 COP/month.',
				'Recruiter Business: 199,000 COP/month.',
				'Recruiter Agency: 499,000 COP/month.'
			],
			blocks: [
				{
					title: 'Payments',
					paragraphs: [
						'Payments are processed through enabled gateways (currently Wompi and Mercado Pago). eptus does not receive or store card numbers: the charge is performed by the gateway under its own terms, security and support, which also apply when you use it.',
						'Plan limits renew each calendar month and do not roll over to the next period.'
					]
				}
			]
		},
		{
			id: 'cancelacion-reembolsos',
			title: 'Renewal, cancellation and refunds',
			bullets: [
				'A paid plan covers a monthly period counted from payment confirmation. You can check your plan status on the Plan page of your account.',
				'You may cancel at any time from the Plan page: you keep access until the end of the period already paid, then move to the free plan. Your résumé and history are preserved.',
				'Withdrawal and refunds: under the Colombian Consumer Statute (Law 1480 of 2011, article 47), you may exercise the right of withdrawal within five (5) business days following the purchase, unless the service has already started being performed with your agreement. In practice: we process a full refund if you contact eptus.asistcv@gmail.com within that window and have not consumed the paid benefits of your plan. If you already consumed plan benefits, withdrawal does not apply because the service was already performed.',
				'Duplicate or erroneous charges are refunded or corrected through the same payment method within a maximum of thirty (30) calendar days.'
			]
		},
		{
			id: 'propiedad-intelectual',
			title: 'Intellectual property',
			paragraphs: [
				'The Platform, its software, design, texts and the eptus and AsistCV trademarks belong to their owner and operator. We grant you a personal, limited, non-transferable and revocable license to use the service solely in accordance with these Terms.',
				'Your résumés, job descriptions and approved adaptations are yours, and you decide how to use them.',
				'If you share feedback or suggestions, you authorize us to use them to improve the product, without obligation of compensation.'
			]
		},
		{
			id: 'ia-resultados',
			title: 'Nature of results and artificial intelligence',
			bullets: [
				'Analyses and adaptations are generated with artificial intelligence systems and may contain errors or omissions: they are an indicative recommendation, not a definitive truth.',
				'The anti-hallucination validator reduces the risk of an adaptation inventing experience, but does not eliminate it entirely. Always review and approve content before using it.',
				'We do not guarantee job outcomes, interviews or hiring.'
			]
		},
		{
			id: 'disponibilidad',
			title: 'Availability, support and suspensions',
			bullets: [
				'The Platform is provided «as is», with reasonable effort toward availability. Interruptions may occur due to maintenance or third-party dependencies.',
				'Support is provided at eptus.asistcv@gmail.com.',
				'We may suspend or disable accounts that breach these Terms, with prior notice when possible.',
				'You may terminate your account at any time; subsequent data processing is governed by the Privacy Policy.'
			]
		},
		{
			id: 'responsabilidad',
			title: 'Limitation of liability',
			paragraphs: [
				'To the maximum extent permitted by Colombian law, eptus is not liable for indirect or incidental damages, lost profits or loss of information beyond its reasonable control.',
				'eptus\' total liability for any claim is limited to the amount you actually paid for the Platform in the three (3) months preceding the event giving rise to liability.'
			]
		},
		{
			id: 'cambios',
			title: 'Changes to these Terms',
			paragraphs: [
				'New versions are published on this page, with version number and date. Substantive changes are announced at least fifteen (15) days in advance within the Platform or to the registered email address.',
				'If you keep using the Platform after a new version takes effect, you are deemed to accept it. If you do not agree, stop using the Platform and cancel your plan.'
			]
		},
		{
			id: 'ley-aplicable',
			title: 'Governing law and dispute resolution',
			bullets: [
				'These Terms are governed by the laws of the Republic of Colombia.',
				'As a consumer, you are entitled to the guarantees of the Consumer Statute and may resort to the Superintendence of Industry and Commerce.',
				'Any dispute will first be addressed amicably, within the thirty (30) days following notice. If no agreement is reached, the Colombian courts at the operator\'s domicile have jurisdiction.'
			]
		},
		{
			id: 'contacto',
			title: 'Contact',
			paragraphs: ['Questions, support and claims: eptus.asistcv@gmail.com.']
		}
	]
};

// =====================================================================
// POLÍTICA DE TRATAMIENTO DE DATOS PERSONALES
// =====================================================================

const privacyEs: LegalDoc = {
	version: '1.0',
	meta: `Versión 1.0 · Última actualización: ${UPDATED_DATE_ES}`,
	title: 'Política de Privacidad y Tratamiento de Datos Personales',
	intro: [
		'Esta Política describe cómo eptus trata los datos personales en AsistCV, conforme a la Ley 1581 de 2012 y el Decreto 1377 de 2013 de Colombia.',
		'Redactamos esta Política para que se entera sola: qué datos guardamos, para qué, con quién los compartimos, cuánto tiempo y cómo ejercer sus derechos.'
	],
	sections: [
		{
			id: 'responsable',
			title: 'Responsable del tratamiento',
			paragraphs: [
				'«eptus» es operado por Daniel Elias Cordoba Howard, mayor de edad, identificado con cédula de ciudadanía No. 1123890948 (persona natural; a la fecha no existe sociedad registrada), quien actúa como responsable del tratamiento de sus datos personales. Canal de atención: eptus.asistcv@gmail.com.'
			]
		},
		{
			id: 'datos',
			title: 'Datos que tratamos',
			bullets: [
				'Cuenta: correo electrónico, nombre, idioma preferido y fechas de creación y último acceso.',
				'Hojas de vida: el PDF original, el texto extraído, los datos estructurados que el sistema interpreta del documento (nombre, experiencia, habilidades) y representaciones numéricas (embeddings) calculadas a partir de su contenido.',
				'Vacantes: el texto que usted pega y los metadatos que se detectan (cargo, empresa).',
				'Análisis e historial: puntaje, fortalezas, brechas, recomendación de energía y una copia de su perfil al momento de cada análisis, para que los resultados sean reproducibles.',
				'Auditoría sin registro: el texto de la hoja de vida y de la vacante analizadas, un identificador anónimo, un hash de su dirección IP y su navegador. Se conservan máximo treinta (30) días. Solo guardamos su correo electrónico si usted decide dejarlo para recuperar el resultado.',
				'Seguridad: intentos de acceso (correo e IP), eventos de seguridad y tokens de sesión, que se almacenan solo como hash.',
				'Pagos: plan, estado de la suscripción e historial de pagos (monto, fecha, estado). No recibimos ni almacenamos números de tarjeta: eso lo procesan las pasarelas de pago.',
				'Reclutadores: hojas de vida de candidatos externos que el reclutador carga, y el registro de su aceptación de los términos del rol.',
				'Alertas: sus preferencias de notificación de ofertas de empleo.'
			]
		},
		{
			id: 'finalidades',
			title: 'Finalidades del tratamiento',
			bullets: [
				'Prestar el servicio: calcular matches, producir adaptaciones y mantener su historial.',
				'Enviar códigos de acceso y, si usted lo activa, alertas de ofertas.',
				'Seguridad: prevenir fraude, abuso y accesos no autorizados.',
				'Facturación y cobro de los planes pagos.',
				'Soporte y respuesta a solicitudes.',
				'Mejorar el producto con métricas agregadas o anonimizadas.'
			],
			blocks: [
				{
					title: 'Lo que NO hacemos',
					paragraphs: [
						'No vendemos sus datos. No los usamos para publicidad. No los usamos para entrenar modelos de inteligencia artificial propios ni de terceros.'
					]
				}
			]
		},
		{
			id: 'autorizacion',
			title: 'Autorización y datos sensibles',
			paragraphs: [
				'El tratamiento se apoya en su autorización previa, expresa e informada, que usted otorga al crear su cuenta o usar la Plataforma, conforme al artículo 9 de la Ley 1581 de 2012. Puede revocarla en cualquier momento por los canales indicados abajo, salvo que exista una obligación legal o contractual pendiente (por ejemplo, registros de facturación).',
				'No pedimos ni necesitamos datos sensibles (salud, origen racial o étnico, religión, afiliación política, entre otros). Le pedimos que no incluya ese tipo de información en su hoja de vida: no es necesaria para el análisis.'
			]
		},
		{
			id: 'menores',
			title: 'Menores de edad',
			paragraphs: [
				'El servicio está dirigido exclusivamente a personas mayores de 18 años. No tratamos datos de menores de edad; si nos escribe a eptus.asistcv@gmail.com, eliminamos la cuenta y los datos asociados.'
			]
		},
		{
			id: 'candidatos-reclutador',
			title: 'Candidatos cargados por reclutadores',
			paragraphs: [
				'Si usted es un candidato cuya hoja de vida fue cargada por un reclutador: el reclutador declara y garantiza que cuenta con su autorización para tratar sus datos en la Plataforma. Usted puede ejercer sus derechos escribiéndonos a eptus.asistcv@gmail.com, y atenderemos su solicitud coordinándonos con la cuenta reclutadora.'
			]
		},
		{
			id: 'encargados',
			title: 'Encargados del tratamiento y transferencia internacional',
			paragraphs: [
				'Para operar la Plataforma compartimos sus datos únicamente con los siguientes encargados, bajo compromisos de confidencialidad y seguridad y solo para las finalidades descritas:'
			],
			bullets: [
				'Neon — base de datos PostgreSQL donde se aloja la información.',
				'Render — servidores de la aplicación (backend y API).',
				'Cloudflare — distribución del sitio (frontend y red de entrega).',
				'Google (Gemini API) — generación de representaciones numéricas de hojas de vida y vacantes.',
				'Groq — procesamiento de lenguaje para análisis y adaptación.',
				'Resend — envío de correos electrónicos (códigos de acceso y alertas).',
				'Wompi y Mercado Pago — procesamiento de pagos.'
			],
			blocks: [
				{
					title: 'Transferencia internacional',
					paragraphs: [
						'Algunos de estos proveedores operan en servidores ubicados fuera de Colombia. La transferencia internacional se realiza exclusivamente hacia los encargados listados, que adoptan compromisos de confidencialidad y seguridad equivalentes a los exigidos por la normativa colombiana. Nunca vendemos sus datos.'
					]
				}
			]
		},
		{
			id: 'conservacion',
			title: 'Plazos de conservación y supresión',
			bullets: [
				'Cuenta, hoja de vida e historial: mientras su cuenta esté activa. Puede borrar su hoja de vida desde la aplicación y eliminar su cuenta escribiendo a eptus.asistcv@gmail.com; la supresión se ejecuta en máximo treinta (30) días y en copias de respaldo en máximo noventa (90) días.',
				'Auditorías sin registro: máximo treinta (30) días, con purga automática.',
				'Códigos de acceso y tokens de sesión: horas o días, según su función.',
				'Registros de seguridad: hasta doce (12) meses.',
				'Registros de facturación: los plazos que exija la normativa fiscal y comercial colombiana.'
			]
		},
		{
			id: 'derechos',
			title: 'Sus derechos y cómo ejercerlos',
			paragraphs: [
				'Como titular de los datos, conforme al artículo 8 de la Ley 1581 de 2012, usted puede: conocer y acceder a sus datos, actualizarlos y rectificarlos, solicitar prueba de la autorización otorgada, revocar la autorización y solicitar la supresión de sus datos. El trámite es gratuito.'
			],
			blocks: [
				{
					title: 'Canales',
					paragraphs: [
						'Varias acciones puede hacerlas usted mismo desde la Plataforma: borrar su hoja de vida, editar sus datos y cancelar su plan. Para lo demás, escriba a eptus.asistcv@gmail.com; respondemos en máximo diez (10) días hábiles, prorrogables por diez (10) días más cuando la solicitud lo requiera.'
					]
				}
			]
		},
		{
			id: 'seguridad',
			title: 'Seguridad de la información',
			bullets: [
				'Transmisiones cifradas (TLS) entre su navegador y la Plataforma.',
				'Tokens de sesión y códigos guardados solo como hash criptográfico.',
				'Hash de la dirección IP en auditorías anónimas, sin guardar la IP en texto claro.',
				'Control de acceso por usuario y rol en la base de datos (aislamiento por fila), de modo que nadie más ve su hoja de vida ni su historial.',
				'Cifrado en reposo administrado por el proveedor de base de datos.',
				'Si detectamos una vulneración que comprometa sus datos, la notificaremos a usted y a la autoridad competente cuando la normativa lo exija.'
			]
		},
		{
			id: 'cambios',
			title: 'Cambios a esta Política',
			paragraphs: [
				'Publicamos nuevas versiones en esta página, con número de versión y fecha. Si un cambio requiere una autorización adicional según la ley, la solicitaremos de forma expresa antes de ejecutarlo.'
			]
		},
		{
			id: 'autoridad',
			title: 'Autoridad de control',
			paragraphs: [
				'Si considera que sus derechos no han sido atendidos, puede acudir a la Superintendencia de Industria y Comercio — Delegatura para la Protección de Datos Personales (Colombia).'
			]
		},
		{
			id: 'contacto',
			title: 'Contacto',
			paragraphs: [
				'Solicitudes, consultas y reclamos de datos personales: eptus.asistcv@gmail.com.'
			]
		}
	]
};

const privacyEn: LegalDoc = {
	version: '1.0',
	meta: `Version 1.0 · Last updated: ${UPDATED_DATE_EN}`,
	title: 'Privacy and Personal Data Processing Policy',
	intro: [
		'This Policy describes how eptus processes personal data on AsistCV, in accordance with Colombian Law 1581 of 2012 and Decree 1377 of 2013.',
		'We wrote it to be read on its own: what data we keep, why, who we share it with, for how long and how to exercise your rights.'
	],
	sections: [
		{
			id: 'responsable',
			title: 'Data controller',
			paragraphs: [
				'«eptus» is operated by Daniel Elias Cordoba Howard, of legal age, identified with Colombian citizenship card (cédula de ciudadanía) No. 1123890948 (natural person; no registered company yet), who acts as controller of your personal data. Support channel: eptus.asistcv@gmail.com.'
			]
		},
		{
			id: 'datos',
			title: 'Data we process',
			bullets: [
				'Account: email address, name, preferred language, creation and last-login dates.',
				'Résumés: the original PDF, the extracted text, the structured data the system interprets from the document (name, experience, skills) and numerical representations (embeddings) computed from its content.',
				'Job descriptions: the text you paste and the metadata detected from it (title, company).',
				'Analyses and history: score, strengths, gaps, energy recommendation and a copy of your profile at the time of each analysis, so results are reproducible.',
				'Unregistered audit: the text of the analyzed résumé and job description, an anonymous identifier, a hash of your IP address and your browser. Kept for a maximum of thirty (30) days. We only store your email if you choose to leave it to recover the result.',
				'Security: login attempts (email and IP), security events and session tokens, which are stored only as hashes.',
				'Payments: plan, subscription status and payment history (amount, date, status). We do not receive or store card numbers: payment gateways process those.',
				'Recruiters: résumés of external candidates uploaded by the recruiter, and the record of their acceptance of the role terms.',
				'Alerts: your job-offer notification preferences.'
			]
		},
		{
			id: 'finalidades',
			title: 'Purposes of processing',
			bullets: [
				'Providing the service: computing matches, producing adaptations and maintaining your history.',
				'Sending access codes and, if you enable it, job alerts.',
				'Security: preventing fraud, abuse and unauthorized access.',
				'Billing and collection for paid plans.',
				'Support and responding to requests.',
				'Improving the product with aggregated or anonymized metrics.'
			],
			blocks: [
				{
					title: 'What we do NOT do',
					paragraphs: [
						'We do not sell your data. We do not use it for advertising. We do not use it to train artificial intelligence models of our own or of third parties.'
					]
				}
			]
		},
		{
			id: 'autorizacion',
			title: 'Authorization and sensitive data',
			paragraphs: [
				'Processing relies on your prior, express and informed authorization, granted when you create your account or use the Platform, in accordance with article 9 of Law 1581 of 2012. You may revoke it at any time through the channels indicated below, unless a legal or contractual obligation remains (for example, billing records).',
				'We do not ask for or need sensitive data (health, racial or ethnic origin, religion, political affiliation, among others). Please do not include that kind of information in your résumé: it is not needed for the analysis.'
			]
		},
		{
			id: 'menores',
			title: 'Minors',
			paragraphs: [
				'The service is intended exclusively for persons aged 18 or older. We do not process data of minors; if you contact us, we delete the account and its associated data.'
			]
		},
		{
			id: 'candidatos-reclutador',
			title: 'Candidates uploaded by recruiters',
			paragraphs: [
				'If you are a candidate whose résumé was uploaded by a recruiter: the recruiter declares and warrants that they have your authorization to process your data on the Platform. You may exercise your rights by writing to eptus.asistcv@gmail.com, and we will handle your request in coordination with the recruiter account.'
			]
		},
		{
			id: 'encargados',
			title: 'Data processors and international transfer',
			paragraphs: [
				'To operate the Platform we share your data only with the following processors, under confidentiality and security commitments and solely for the purposes described:'
			],
			bullets: [
				'Neon — PostgreSQL database hosting the information.',
				'Render — application servers (backend and API).',
				'Cloudflare — site delivery (frontend and content delivery network).',
				'Google (Gemini API) — generation of numerical representations of résumés and job descriptions.',
				'Groq — language processing for analysis and adaptation.',
				'Resend — email delivery (access codes and alerts).',
				'Wompi and Mercado Pago — payment processing.'
			],
			blocks: [
				{
					title: 'International transfer',
					paragraphs: [
						'Some of these providers operate servers located outside Colombia. International transfer occurs exclusively to the processors listed above, which adopt confidentiality and security commitments equivalent to those required by Colombian law. We never sell your data.'
					]
				}
			]
		},
		{
			id: 'conservacion',
			title: 'Retention and deletion periods',
			bullets: [
				'Account, résumé and history: while your account is active. You can delete your résumé from the application and remove your account by writing to eptus.asistcv@gmail.com; deletion is executed within a maximum of thirty (30) days, and within a maximum of ninety (90) days in backup copies.',
				'Unregistered audits: a maximum of thirty (30) days, with automatic purging.',
				'Access codes and session tokens: hours or days, depending on their function.',
				'Security records: up to twelve (12) months.',
				'Billing records: the periods required by Colombian tax and commercial law.'
			]
		},
		{
			id: 'derechos',
			title: 'Your rights and how to exercise them',
			paragraphs: [
				'As a data subject, under article 8 of Law 1581 of 2012 you may: know and access your data, update and rectify them, request proof of the authorization granted, revoke the authorization and request deletion of your data. The procedure is free of charge.'
			],
			blocks: [
				{
					title: 'Channels',
					paragraphs: [
						'Several actions you can take yourself from the Platform: delete your résumé, edit your data and cancel your plan. For everything else, write to eptus.asistcv@gmail.com; we respond within a maximum of ten (10) business days, extendable by ten (10) more days when the request requires it.'
					]
				}
			]
		},
		{
			id: 'seguridad',
			title: 'Information security',
			bullets: [
				'Encrypted transmissions (TLS) between your browser and the Platform.',
				'Session tokens and codes stored only as cryptographic hashes.',
				'Hashed IP addresses in anonymous audits, never stored in plain text.',
				'User and role-based access control in the database (row-level isolation), so nobody else sees your résumé or history.',
				'Encryption at rest managed by the database provider.',
				'If we detect a breach affecting your data, we will notify you and the competent authority as required by law.'
			]
		},
		{
			id: 'cambios',
			title: 'Changes to this Policy',
			paragraphs: [
				'New versions are published on this page, with version number and date. If a change requires additional authorization under the law, we will request it expressly before executing it.'
			]
		},
		{
			id: 'autoridad',
			title: 'Supervisory authority',
			paragraphs: [
				'If you believe your rights have not been addressed, you may resort to the Superintendence of Industry and Commerce — Delegation for Personal Data Protection (Colombia).'
			]
		},
		{
			id: 'contacto',
			title: 'Contact',
			paragraphs: [
				'Personal data requests, inquiries and claims: eptus.asistcv@gmail.com.'
			]
		}
	]
};

// =====================================================================
// POLÍTICA DE COOKIES
// =====================================================================

const cookiesEs: LegalDoc = {
	version: '1.0',
	meta: `Versión 1.0 · Última actualización: ${UPDATED_DATE_ES}`,
	title: 'Política de Cookies y Almacenamiento Local',
	intro: [
		'En resumen: no usamos cookies de publicidad ni de seguimiento, ni herramientas de analítica de terceros. La Plataforma guarda un mínimo de información técnica en el almacenamiento local de su navegador (localStorage), no en cookies.'
	],
	sections: [
		{
			id: 'que-guardamos',
			title: 'Qué guardamos y para qué',
			paragraphs: [
				'Estas son las claves que la Plataforma guarda en el almacenamiento local de su navegador, todas estrictamente funcionales:'
			],
			bullets: [
				'asistcv.session — su sesión: tokens de acceso y datos básicos de su cuenta. Perdura hasta que usted cierre sesión; al cerrarla se elimina.',
				'asistcv.locale — su idioma preferido (español o inglés).',
				'asistcv.audit_token — identificador anónimo de su auditoría sin registro. Se elimina al reclamar la auditoría con una cuenta o al expirar (máximo 30 días).',
				'asistcv.onboarding y asistcv.activeProfileId — preferencias de uso de la aplicación (onboarding completado, perfil activo).'
			]
		},
		{
			id: 'terceros',
			title: 'Cookies de terceros',
			paragraphs: [
				'Nuestra infraestructura de entrega (Cloudflare) puede establecer cookies técnicas estrictamente necesarias para seguridad y equilibrio de carga, sin fines de seguimiento ni publicidad.'
			]
		},
		{
			id: 'eliminar',
			title: 'Cómo eliminar esta información',
			paragraphs: [
				'Puede borrar los datos del sitio desde la configuración de su navegador (borrar datos de navegación o datos del sitio), o simplemente cerrar sesión en la Plataforma, lo que elimina la clave de sesión. Sin esa información, deberá iniciar sesión de nuevo y su navegador volverá al idioma por defecto.'
			]
		},
		{
			id: 'cambios',
			title: 'Cambios a esta Política',
			paragraphs: [
				'Publicamos nuevas versiones en esta página, con número de versión y fecha.'
			]
		}
	]
};

const cookiesEn: LegalDoc = {
	version: '1.0',
	meta: `Version 1.0 · Last updated: ${UPDATED_DATE_EN}`,
	title: 'Cookie and Local Storage Policy',
	intro: [
		'In short: we use no advertising or tracking cookies, and no third-party analytics tools. The Platform stores a minimal amount of technical information in your browser\'s local storage (localStorage), not in cookies.'
	],
	sections: [
		{
			id: 'que-guardamos',
			title: 'What we store and why',
			paragraphs: [
				'These are the keys the Platform stores in your browser\'s local storage, all strictly functional:'
			],
			bullets: [
				'asistcv.session — your session: access tokens and basic account data. It persists until you log out, at which point it is deleted.',
				'asistcv.locale — your preferred language (Spanish or English).',
				'asistcv.audit_token — anonymous identifier of your unregistered audit. It is deleted when you claim the audit with an account or when it expires (maximum 30 days).',
				'asistcv.onboarding and asistcv.activeProfileId — application usage preferences (onboarding completed, active profile).'
			]
		},
		{
			id: 'terceros',
			title: 'Third-party cookies',
			paragraphs: [
				'Our delivery infrastructure (Cloudflare) may set strictly necessary technical cookies for security and load balancing, with no tracking or advertising purposes.'
			]
		},
		{
			id: 'eliminar',
			title: 'How to delete this information',
			paragraphs: [
				'You can clear site data from your browser settings (clear browsing or site data), or simply log out of the Platform, which removes the session key. Without that information, you will need to log in again and your browser will return to the default language.'
			]
		},
		{
			id: 'cambios',
			title: 'Changes to this Policy',
			paragraphs: [
				'New versions are published on this page, with version number and date.'
			]
		}
	]
};

/** Documentos legales por idioma. Fallback de lectura: español. */
export const LEGAL_DOCS: Record<'es' | 'en', Record<LegalDocKind, LegalDoc>> = {
	es: { terms: termsEs, privacy: privacyEs, cookies: cookiesEs },
	en: { terms: termsEn, privacy: privacyEn, cookies: cookiesEn }
};

/** Documento legal para un locale dado, con fallback a español. */
export function getLegalDoc(kind: LegalDocKind, locale: string | null | undefined): LegalDoc {
	return locale === 'en' ? LEGAL_DOCS.en[kind] : LEGAL_DOCS.es[kind];
}
