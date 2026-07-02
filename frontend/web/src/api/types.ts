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
