/**
 * Tipos del dominio. Son espejo de los schemas Pydantic del backend
 * (`backend/app/llm/schemas.py` y `backend/app/api/v1/analyses.py`).
 * Si el backend cambia un campo, actualizar este archivo y verificar
 * el AC del PR.
 */

export type EnergyLevel = 'low' | 'medium' | 'high';
export type MatchMode = 'complete' | 'retrieved';

export interface MatchAnalysis {
	score: number;
	strengths: string[];
	gaps: string[];
	energy_level: EnergyLevel;
	reasoning: string;
	mode?: MatchMode;
	chunks_used?: number | null;
}

export interface AnalysisSummary {
	id: number;
	profile_id: number | null;
	job_description_id: number;
	score: number | null;
	created_at: string;
}

export interface JobDescriptionEmbedded {
	id: number;
	title: string | null;
	company: string | null;
	snippet: string;
}

export interface AnalysisDetail {
	id: number;
	profile_id: number | null;
	job_description_id: number;
	score: number | null;
	strengths: string[];
	gaps: string[];
	energy_level: string | null;
	reasoning: string | null;
	created_at: string;
	job_description: JobDescriptionEmbedded;
}

export interface Profile {
	id: number;
	title?: string | null;
}

export interface MatchRequest {
	jd_text: string;
	profile_id: number;
}

export interface PaginatedAnalyses<T> {
	items: T[];
	limit: number;
	offset: number;
	total: number;
}

// === Sprint 2: accounts, CVs, recruiter, billing, audit ===

export type Role = 'job_seeker' | 'recruiter';

export interface TokenResponse {
	access_token: string;
	refresh_token: string;
	token_type: string;
}

export interface SignUpPayload {
	email: string;
	password: string;
	role: Role;
	full_name: string;
	locale: string;
	accept_tos: boolean;
	good_faith_declaration: boolean;
	tos_version: string;
}

export interface SessionUser {
	id: number;
	email: string;
	role: Role;
	full_name: string;
	locale: string;
	email_verified_at?: string | null;
}

export interface CVStructuredData {
	full_name: string;
	email?: string | null;
	phone?: string | null;
	location?: string | null;
	experience: Record<string, unknown>[];
	education: Record<string, unknown>[];
	skills: string[];
	languages?: Record<string, unknown>[];
}

export interface CVSummary {
	id: number;
	original_filename: string;
	detected_locale: string | null;
	created_at: string;
	last_edited_at: string;
}

export interface CVDetail extends CVSummary {
	structured: Record<string, unknown>;
	raw_text: string | null;
}

export interface CVUploadResult {
	cv_id: number;
	original_filename: string;
	detected_locale: string;
	structured: Record<string, unknown>;
}

export interface Candidate {
	id: number;
	recruiter_id: number;
	full_name: string;
	email: string | null;
	phone: string | null;
	notes: string | null;
	cv_id: number | null;
	last_analysed_at: string | null;
	created_at: string;
}

export interface CandidateListResponse {
	items: Candidate[];
	total: number;
	page: number;
	page_size: number;
	has_more: boolean;
}

export interface CandidateMatchResult {
	candidate_id: number;
	score: number | null;
	reasoning: string | null;
	created_at: string;
}

export interface RankedCandidates {
	items: Candidate[];
	total: number;
	effective_scores: Record<string, number>;
	total_candidates: number;
	is_truncated: boolean;
}

export interface ConsentState {
	accepted_at: string;
	tos_version: string;
}

export interface Plan {
	plan_id: string;
	name: string;
	tier: string;
	price_cents: number;
	currency: string;
	interval: string;
	features: string[];
	limits: Record<string, unknown>;
}

export interface SubscriptionInfo {
	plan_id: string;
	status: string;
	current_period_end: string | null;
	limits: Record<string, unknown>;
	usage: Record<string, unknown>;
	overage: number;
}

export interface AuditAnonymousResult {
	audit_token: string;
	score: number;
	strengths: string[];
	gaps: string[];
	energy_level: string;
	reasoning: string;
}

export class ApiError extends Error {
	readonly status: number;
	readonly cause?: string;
	readonly code?: string;
	readonly retryAfter?: number;

	constructor(message: string, status: number, cause?: string, code?: string, retryAfter?: number) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
		this.cause = cause;
		this.code = code;
		this.retryAfter = retryAfter;
	}
}