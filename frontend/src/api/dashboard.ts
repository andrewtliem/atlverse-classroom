import { supabase } from './supabase';

export interface UserProfile {
  first_name: string;
  last_name: string;
}

export interface MaterialInfo {
  id: number;
}

export interface SelfEvaluation {
  completed_at: string | null;
  started_at: string | null;
  score: number | null;
  quiz_id: number | null;
  student_id: number;
  material_id: number | null;
  classroom_id: number;
  is_ai_generated: boolean;
  material: { title: string } | null;
  quiz: { title: string; passing_score: number } | null;
}

export interface Quiz {
  id: number;
  title: string;
  time_limit_minutes: number | null;
  published: boolean;
  available_from: string | null;
  available_until: string | null;
  evaluations: SelfEvaluation[];
}

export interface AssignmentSubmission {
  student_id: number;
  assignment_id: number;
  submitted_at: string;
  grade: number | null;
}

export interface Assignment {
  id: number;
  title: string;
  deadline: string | null;
  published: boolean;
  submissions: AssignmentSubmission[];
}

export interface ClassroomData {
  id: number;
  name: string;
  description: string | null;
  invitation_code: string;
  teacher: UserProfile;
  material: MaterialInfo[];
  quiz: Quiz[];
  assignment: Assignment[];
  enrollment: { student_id: number }[];
}

export interface ProcessedClassroom extends ClassroomData {
  materials_count: number;
  quiz_stats: {
    pending: number;
    completed: number;
  };
  quizzes_with_status: { quiz: Quiz; status: string }[];
  assignment_stats: { active_now: number };
  assignments_with_status: { assignment: Assignment; status: string }[];
  gold_medal_count: number;
  num_students_in_ranking: number;
  gold_rank: number;
  teacher_full_name: string;
}

export interface AiQuizAwardInfo {
  material_title: string;
  score: number;
  attempts: number;
  award: string;
}

export interface DashboardOutput {
  classrooms: ProcessedClassroom[];
  ai_quiz_awards: { [classroomId: number]: { [materialId: number]: AiQuizAwardInfo } };
  classroom_names: { [classroomId: number]: string };
}

export async function getStudentDashboardData(): Promise<DashboardOutput> {
  try {
    const currentUserEmail = (await supabase.auth.getSession()).data.session?.user.email;
    if (!currentUserEmail) throw new Error("User not logged in or email not available.");

    // Fetch the integer user_id from the public.user table using the email
    const { data: publicUser, error: publicUserError } = await supabase
      .from('user')
      .select('id')
      .eq('email', currentUserEmail)
      .single();

    if (publicUserError || !publicUser) {
      throw new Error("Failed to retrieve public user ID from Supabase using email.");
    }
    const currentUserId = publicUser.id; // This will be the integer ID

    // First, get the classroom IDs the student is enrolled in
    const { data: enrollments, error: enrollmentsError } = await supabase
      .from('enrollment')
      .select('classroom_id')
      .eq('student_id', currentUserId);

    if (enrollmentsError) throw enrollmentsError;

    const enrolledClassroomIds = enrollments.map(enrollment => enrollment.classroom_id);

    // If the student is not enrolled in any classrooms, return empty data
    if (enrolledClassroomIds.length === 0) {
      return {
        classrooms: [],
        ai_quiz_awards: {},
        classroom_names: {},
      };
    }

    const { data: classrooms, error: classroomsError } = await supabase
      .from('classroom')
      .select(
        `
        id, name, description, invitation_code, created_at, teacher:user(first_name, last_name),
        material(id),
        quiz(id, title, time_limit_minutes, published, available_from, available_until, evaluations:self_evaluation(completed_at, started_at, score, quiz_id, student_id, quiz(passing_score))),
        assignment(id, title, deadline, published, submissions:assignment_submission(student_id, assignment_id, submitted_at, grade)),
        enrollment(student_id)
        `
      )
      .in('id', enrolledClassroomIds)
      .order('created_at', { ascending: false }) as { data: ClassroomData[] | null; error: any };

    if (classroomsError) throw classroomsError;
    if (!classrooms) throw new Error("No classroom data returned.");

    const { data: aiQuizAwards, error: aiQuizAwardsError } = await supabase
      .from('self_evaluation')
      .select(
        `
        *,
        material:material(title),
        quiz:quiz(title)
        `
      )
      .eq('is_ai_generated', true)
      .in('classroom_id', enrolledClassroomIds) as { data: SelfEvaluation[] | null; error: any };

    if (aiQuizAwardsError) throw aiQuizAwardsError;
    if (!aiQuizAwards) throw new Error("No AI quiz awards data returned.");

    const processedClassrooms: ProcessedClassroom[] = classrooms.map((classroom: ClassroomData) => {
      const quizStats = {
        pending: 0,
        completed: 0,
      };

      const quizzesWithStatus = classroom.quiz.map((quiz: Quiz) => {
        const studentEvaluation = quiz.evaluations.find(
          (evalItem: SelfEvaluation) => evalItem.student_id === currentUserId && evalItem.quiz_id === quiz.id
        );
        let status = 'Not Taken';

        if (studentEvaluation) {
          if (studentEvaluation.completed_at) {
            status = 'Completed';
            quizStats.completed++;
          } else if (studentEvaluation.started_at) {
            status = 'In Progress';
            quizStats.pending++;
          }
        } else {
          const now = new Date();
          const availableFrom = quiz.available_from ? new Date(quiz.available_from) : null;
          const availableUntil = quiz.available_until ? new Date(quiz.available_until) : null;

          if (quiz.published) {
            if ((!availableFrom || now >= availableFrom) && (!availableUntil || now <= availableUntil)) {
              status = 'Available';
              quizStats.pending++;
            } else if (availableFrom && now < availableFrom) {
              status = 'Upcoming';
            } else if (availableUntil && now > availableUntil) {
              status = 'Expired';
            }
          }
        }

        return { quiz, status };
      });

      const assignmentStats = { active_now: 0 };
      const assignmentsWithStatus = classroom.assignment.map((assignment: Assignment) => {
        const submission = assignment.submissions.find((sub: AssignmentSubmission) => sub.student_id === currentUserId);
        let status = 'Not Submitted';

        if (submission) {
          status = 'Submitted';
        } else {
          const now = new Date();
          const deadline = assignment.deadline ? new Date(assignment.deadline) : null;

          if (assignment.published) {
            if (deadline && now > deadline) {
              status = 'Expired';
            } else {
              status = 'Active';
              assignmentStats.active_now++;
            }
          }
        }
        return { assignment, status };
      });

      let goldMedalCount = 0;
      // Simplified ranking: this would typically require a backend function or more complex query
      const studentSelfEvaluationsForAwards = aiQuizAwards.filter(
        (evalItem: SelfEvaluation) =>
          evalItem.student_id === currentUserId &&
          evalItem.classroom_id === classroom.id &&
          evalItem.score !== null &&
          evalItem.score >= 80 && // Gold award condition
          evalItem.material_id !== null // Ensure it's tied to a material
      );
      goldMedalCount = studentSelfEvaluationsForAwards.length;
      
      const teacherFullName = classroom.teacher ? `${classroom.teacher.first_name} ${classroom.teacher.last_name}` : 'N/A';

      return {
        ...classroom,
        teacher: classroom.teacher || { first_name: 'N/A', last_name: 'N/A' },
        materials_count: classroom.material.length,
        quiz_stats: quizStats,
        quizzes_with_status: quizzesWithStatus,
        assignment_stats: assignmentStats,
        assignments_with_status: assignmentsWithStatus,
        gold_medal_count: goldMedalCount,
        num_students_in_ranking: 0, // Placeholder for ranking
        gold_rank: 0, // Placeholder for ranking
        teacher_full_name: teacherFullName,
      };
    });

    const processedAiQuizAwards: { [classroomId: number]: { [materialId: number]: AiQuizAwardInfo } } = {};
    const classroomNames: { [classroomId: number]: string } = {};

    processedClassrooms.forEach((c) => {
      classroomNames[c.id] = c.name;
    });

    aiQuizAwards.forEach((award: SelfEvaluation) => {
      if (!award.classroom_id || !award.material_id) return; // Skip if missing required IDs

      if (!processedAiQuizAwards[award.classroom_id]) {
        processedAiQuizAwards[award.classroom_id] = {};
      }
      const materialTitle = award.material ? award.material.title : 'Unknown Material';
      processedAiQuizAwards[award.classroom_id][award.material_id] = {
        material_title: materialTitle,
        score: award.score || 0,
        attempts: 1, // Placeholder: Supabase schema does not directly store attempts per material per student.
        award: award.score !== null && award.score >= 80 ? 'gold' : (award.score !== null && award.score >= 67 ? 'silver' : 'bronze'),
      };
    });

    return {
      classrooms: processedClassrooms,
      ai_quiz_awards: processedAiQuizAwards,
      classroom_names: classroomNames,
    };
  } catch (error) {
    console.error("Error fetching student dashboard data from Supabase:", error);
    throw error;
  }
}

export async function joinClassroom(invitationCode: string) {
  try {
    const { data: classroomData, error: classroomError } = await supabase
      .from('classroom')
      .select('id')
      .eq('invitation_code', invitationCode)
      .single();

    if (classroomError || !classroomData) {
      throw new Error("Invalid invitation code.");
    }

    const currentUserEmail = (await supabase.auth.getSession()).data.session?.user.email;
    if (!currentUserEmail) throw new Error("User not logged in or email not available.");

    // Fetch the integer user_id from the public.user table using the email
    const { data: publicUser, error: publicUserError } = await supabase
      .from('user')
      .select('id')
      .eq('email', currentUserEmail)
      .single();

    if (publicUserError || !publicUser) {
      throw new Error("Failed to retrieve public user ID from Supabase using email.");
    }
    const currentUserId = publicUser.id; // This will be the integer ID

    const { data, error } = await supabase
      .from('enrollment')
      .insert([
        {
          classroom_id: classroomData.id,
          student_id: currentUserId,
        },
      ])
      .select();

    if (error) {
      if (error.code === '23505') { // Unique violation code
        throw new Error("You are already enrolled in this classroom.");
      }
      throw error;
    }
    return data;
  } catch (error: any) {
    console.error("Error joining classroom with Supabase:", error.message);
    throw error;
  }
} 