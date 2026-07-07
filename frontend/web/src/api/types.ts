export interface AuthUser {
  id: string;
  email: string;
  role: "admin" | "jobseeker";
  is_active: boolean;
  created_at: string;
}

export type LanguageProficiency = "native" | "fluent" | "professional" | "intermediate" | "basic";

export interface PersonalInfo {
  first_name?: string | null;
  last_name?: string | null;
  professional_headline?: string | null;
  email?: string | null;
  phone_number?: string | null;
  current_city?: string | null;
  state_province?: string | null;
  country?: string | null;
  willing_to_relocate?: boolean | null;
  preferred_work_locations: string[];
  linkedin_url?: string | null;
  github_url?: string | null;
  portfolio_website?: string | null;
  personal_website?: string | null;
  date_of_birth?: string | null;
  nationality?: string | null;
  work_authorization?: string | null;
}

export const emptyPersonalInfo: PersonalInfo = { preferred_work_locations: [] };

export interface SkillItem {
  id?: string;
  category: string;
  skill_name: string;
  display_order: number;
}

export interface ExperienceProjectItem {
  id?: string;
  project_name: string;
  details: string[];
  display_order: number;
}

export interface ExperienceItem {
  id?: string;
  job_title: string;
  company_name: string;
  employment_type?: string | null;
  location?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  currently_working_here: boolean;
  responsibilities: string[];
  display_order: number;
  projects: ExperienceProjectItem[];
}

export interface ProjectItem {
  id?: string;
  project_name: string;
  details: string[];
  demo_url?: string | null;
  github_url?: string | null;
  display_order: number;
}

export interface EducationItem {
  id?: string;
  degree: string;
  field_of_study?: string | null;
  minor?: string | null;
  institution_name: string;
  university_board?: string | null;
  location?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  graduation_year?: number | null;
  gpa?: string | null;
  honors?: string | null;
  display_order: number;
}

export interface CertificationItem {
  id?: string;
  certification_name: string;
  issuing_organization?: string | null;
  issue_date?: string | null;
  expiry_date?: string | null;
  credential_id?: string | null;
  credential_url?: string | null;
  display_order: number;
}

export interface AchievementItem {
  id?: string;
  achievement_title: string;
  organization?: string | null;
  date_achieved?: string | null;
  description: string[];
  display_order: number;
}

export interface LanguageItem {
  id?: string;
  language: string;
  proficiency: LanguageProficiency;
  display_order: number;
}

export interface ProfileWriteRequest {
  target_job_title: string;
  is_default: boolean;
  professional_summary?: string | null;
  personal_info: PersonalInfo;
  skills: SkillItem[];
  experiences: ExperienceItem[];
  projects: ProjectItem[];
  education: EducationItem[];
  certifications: CertificationItem[];
  achievements: AchievementItem[];
  languages: LanguageItem[];
}

export interface ProfileResponse extends ProfileWriteRequest {
  id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
}

export interface ProfileSummaryResponse {
  id: string;
  user_id: string;
  target_job_title: string;
  is_default: boolean;
  professional_summary?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResumeUploadResponse {
  id: string;
  profile_id: string;
  original_filename: string;
  is_active: boolean;
}

// Mirrors backend agents/resume_parser/schemas.py ResumeParserOutput — same item shapes as
// ProfileWriteRequest (skills, experiences, etc.) minus target_job_title/is_default, which the
// parser has no way to infer from a resume.
export interface ResumeParsedData {
  professional_summary?: string | null;
  personal_info: PersonalInfo;
  skills: SkillItem[];
  experiences: ExperienceItem[];
  projects: ProjectItem[];
  education: EducationItem[];
  certifications: CertificationItem[];
  achievements: AchievementItem[];
  languages: LanguageItem[];
}

export interface ResumeUploadResult {
  resume: ResumeUploadResponse;
  parsed: ResumeParsedData;
}

export type OutreachType = "email" | "linkedin_dm" | "apply_via_link" | "reach_out_other";
export type ApplicationStatus = "extracted" | "draft_ready" | "sent" | "replied";

// Mirrors backend applications/schemas.py::ApplicationResponse.
export interface ApplicationResponse {
  id: string;
  user_id: string;
  profile_id: string | null;
  poster_name: string;
  poster_profile_url: string;
  poster_headline: string | null;
  post_url: string;
  post_timestamp: string | null;
  post_snippet: string;
  was_truncated: boolean;
  company: string | null;
  job_title: string | null;
  skills: string[];
  seniority: string | null;
  location: string | null;
  parsed_email: string | null;
  outreach_type: OutreachType | null;
  outreach_note: string | null;
  drafted_email: { subject: string; body: string } | null;
  final_email_sent: string | null;
  resume_upload_id: string | null;
  relevance_score: number | null;
  relevance_reasoning: string | null;
  is_archived: boolean;
  status: ApplicationStatus;
  sent_at: string | null;
  created_at: string;
  updated_at: string;
}

// Mirrors backend metrics/schemas.py::AgentTokenBreakdown.
export interface AgentTokenBreakdown {
  agent_name: string;
  input_tokens: number;
  output_tokens: number;
}

// Mirrors backend metrics/schemas.py::UserMetricsResponse.
export interface UserMetricsResponse {
  total_applications: number;
  total_applications_this_month: number;
  emails_sent: number;
  drafted_not_sent: number;
  applications_by_status: Record<string, number>;
  most_used_profile: string | null;
  tokens_today: AgentTokenBreakdown[];
  tokens_this_month: AgentTokenBreakdown[];
}

// Mirrors backend metrics/schemas.py::DailyCount / DailyTokenSpend / AgentBreakdown.
export interface DailyCount {
  date: string;
  count: number;
}

export interface DailyTokenSpend {
  date: string;
  input_tokens: number;
  output_tokens: number;
}

export interface AgentBreakdown {
  agent_name: string;
  call_count: number;
  avg_latency_ms: number;
  input_tokens: number;
  output_tokens: number;
}

// Mirrors backend metrics/schemas.py::AdminOverviewResponse.
export interface AdminOverviewResponse {
  total_users: number;
  signups_today: number;
  signups_last_14_days: DailyCount[];
  token_spend_last_14_days: DailyTokenSpend[];
  agent_breakdown: AgentBreakdown[];
}

// Mirrors backend metrics/schemas.py::AdminUserRow.
export interface AdminUserRow {
  id: string;
  email: string;
  created_at: string;
  last_login_at: string | null;
  input_tokens: number;
  output_tokens: number;
  emails_sent: number;
  is_active: boolean;
  access_expires_at: string | null;
  admin_notes: string | null;
}

// Mirrors backend metrics/schemas.py::AdminUserAccessUpdateRequest.
export interface AdminUserAccessUpdateRequest {
  access_expires_at: string | null;
  admin_notes: string | null;
}

// Mirrors backend auth/schemas.py::InviteCodeResponse.
export interface InviteCodeResponse {
  id: string;
  code: string;
  is_used: boolean;
  used_at: string | null;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  used_by_email: string | null;
}

export function emptyProfileDraft(): ProfileWriteRequest {
  return {
    target_job_title: "",
    is_default: false,
    professional_summary: "",
    personal_info: { ...emptyPersonalInfo },
    skills: [],
    experiences: [],
    projects: [],
    education: [],
    certifications: [],
    achievements: [],
    languages: [],
  };
}
