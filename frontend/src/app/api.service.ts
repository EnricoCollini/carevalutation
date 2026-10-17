import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { CalculationResult, Catalog, EvaluationInput, EvaluationListItem, SavedEvaluation } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = '/api';

  private options() {
    const token = localStorage.getItem('auto.session.token') || '';
    return { headers: new HttpHeaders({ 'X-Session-Token': token }) };
  }

  session(nickname: string, password: string): Observable<{ nickname: string; token: string }> {
    return this.http.post<{ nickname: string; token: string }>(`${this.base}/sessions`, { nickname, password });
  }

  catalog(): Observable<Catalog> {
    return this.http.get<Catalog>(`${this.base}/catalog`);
  }

  calculate(input: EvaluationInput): Observable<CalculationResult> {
    return this.http.post<CalculationResult>(`${this.base}/calculate`, input);
  }

  list(): Observable<EvaluationListItem[]> {
    return this.http.get<EvaluationListItem[]>(`${this.base}/evaluations`, this.options());
  }

  get(id: string): Observable<SavedEvaluation> {
    return this.http.get<SavedEvaluation>(`${this.base}/evaluations/${id}`, this.options());
  }

  create(input: EvaluationInput): Observable<SavedEvaluation> {
    return this.http.post<SavedEvaluation>(`${this.base}/evaluations`, input, this.options());
  }

  update(id: string, input: EvaluationInput): Observable<SavedEvaluation> {
    return this.http.put<SavedEvaluation>(`${this.base}/evaluations/${id}`, input, this.options());
  }

  delete(id: string): Observable<unknown> {
    return this.http.delete(`${this.base}/evaluations/${id}`, this.options());
  }
}
