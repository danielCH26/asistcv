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

export class ApiError extends Error {
	readonly status: number;
	readonly cause?: string;

	constructor(message: string, status: number, cause?: string) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
		this.cause = cause;
	}
}