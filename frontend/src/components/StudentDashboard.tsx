import React, { useEffect, useState } from 'react';
import { getStudentDashboardData, joinClassroom } from '../api/dashboard';
import type { ProcessedClassroom, AiQuizAwardInfo, Quiz, Assignment, DashboardOutput } from '../api/dashboard';
// Removed App.css import as it's not specific to this component's styling
// Removed StudentDashboard.css import as we are migrating to Tailwind CSS

interface QuizStats {
  pending: number;
  completed: number;
}

interface AssignmentStats {
  active_now: number;
}

interface QuizInfo {
  quiz: Quiz; 
  status: string;
}

interface AssignmentInfo {
  assignment: Assignment; 
  status: string;
}

type Classroom = ProcessedClassroom;

const StudentDashboard: React.FC = () => {
  const [dashboardData, setDashboardData] = useState<DashboardOutput | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [invitationCode, setInvitationCode] = useState<string>('');
  const [joinClassroomError, setJoinClassroomError] = useState<string | null>(null);
  const [joinClassroomSuccess, setJoinClassroomSuccess] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getStudentDashboardData();
      setDashboardData(data);
    } catch (err) {
      setError('Failed to fetch dashboard data.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleJoinClassroom = async (e: React.FormEvent) => {
    e.preventDefault();
    setJoinClassroomError(null);
    setJoinClassroomSuccess(null);
    try {
      await joinClassroom(invitationCode);
      setJoinClassroomSuccess('Successfully joined classroom!');
      setInvitationCode('');
      fetchData(); // Re-fetch dashboard data after joining
    } catch (err: any) {
      setJoinClassroomError(err.message || 'Failed to join classroom.');
    }
  };

  if (loading) {
    return <div className="text-white text-center py-5">Loading dashboard...</div>;
  }

  if (error) {
    return <div className="text-red-500 text-center py-5">Error: {error}</div>;
  }

  const classrooms = dashboardData?.classrooms || [];
  const aiQuizAwards = dashboardData?.ai_quiz_awards || {};
  const classroomNames = dashboardData?.classroom_names || {};

  return (
    <div className="container mx-auto py-4 px-4">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-white text-2xl font-bold">My Classrooms</h1>
        <button type="button" className="bg-gradient-to-r from-blue-500 to-teal-500 hover:from-blue-600 hover:to-teal-600 text-white font-bold py-2 px-4 rounded-lg shadow-lg flex items-center space-x-2" data-bs-toggle="modal" data-bs-target="#joinClassroomModal">
          <i className="w-5 h-5"></i>
          <span>Join Classroom</span>
        </button>
      </div>

      {classrooms.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {classrooms.map((classroom: Classroom) => (
            <div className="w-full md:w-1/2 lg:w-1/3" key={classroom.id}>
              <div className="bg-dark-bg text-white rounded-2xl shadow-lg overflow-hidden flex flex-col h-full">
                <div className="bg-gradient-blue border-b border-transparent p-4">
                  <h5 className="text-white text-lg font-semibold mb-0 truncate">{classroom.name}</h5>
                </div>
                <div className="p-4 flex flex-col flex-grow">
                  <div className="flex justify-between items-center mb-3">
                    <div>
                      {classroom.quiz_stats.pending > 0 && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-coral text-white mr-2">
                          {classroom.quiz_stats.pending} pending {classroom.quiz_stats.pending === 1 ? 'quiz' : 'quizzes'}
                        </span>
                      )}
                      {classroom.assignment_stats.active_now > 0 && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-500 text-white">
                          {classroom.assignment_stats.active_now} active {classroom.assignment_stats.active_now === 1 ? 'assignment' : 'assignments'}
                        </span>
                      )}
                    </div>
                  </div>

                  {classroom.description && (
                    <p className="text-white-75 mb-3 text-sm line-clamp-2">
                      {classroom.description}
                    </p>
                  )}

                  <div className="mb-3 flex items-center">
                    <small className="text-white-75 text-sm">
                      <i className="w-4 h-4 mr-2"></i>
                      Teacher: {classroom.teacher_full_name || 'N/A'}
                    </small>
                  </div>

                  {classroom.quiz_stats.pending > 0 && (
                    <div className="bg-yellow-500 bg-opacity-20 text-yellow-100 p-2 rounded-lg flex items-center mb-3 text-sm">
                      <i className="w-4 h-4 mr-2"></i>
                      <small className="text-yellow-100">You have {classroom.quiz_stats.pending} {classroom.quiz_stats.pending === 1 ? 'quiz' : 'quizzes'} to complete</small>
                    </div>
                  )}

                  {classroom.quizzes_with_status && classroom.quizzes_with_status.length > 0 && (
                    <div className="mb-3 flex-grow">
                      <h6 className="text-white-80 mb-2 text-base">Class Quizzes:</h6>
                      <ul className="list-none mb-0 text-sm">
                        {classroom.quizzes_with_status.map((quizInfo: QuizInfo) => (
                          <li key={quizInfo.quiz.id} className="flex justify-between items-center py-2 border-b border-gray-700 last:border-b-0">
                            <span className="text-white-75 truncate mr-2">
                              <i className="fas fa-clipboard-list mr-1 text-white-70"></i>
                              {quizInfo.quiz.title}
                              {quizInfo.quiz.time_limit_minutes && (
                                <small className="text-white-50 ml-2">({quizInfo.quiz.time_limit_minutes} min)</small>
                              )}
                            </span>
                            {quizInfo.status === 'Available' ? (
                              <a href={`/student/classroom/${classroom.id}/quiz/${quizInfo.quiz.id}`} className="bg-gradient-teal hover:from-teal-600 hover:to-cyan-700 text-white text-xs font-bold py-1.5 px-3 rounded-lg flex-shrink-0">
                                Take Quiz
                              </a>
                            ) : (
                              <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                quizInfo.status === 'Completed' ? 'bg-green-500' : 
                                quizInfo.status === 'Upcoming' ? 'bg-blue-500' : 
                                quizInfo.status === 'Expired' ? 'bg-red-500' : 
                                'bg-gray-500'
                              } flex-shrink-0`}>
                                {quizInfo.status}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {classroom.assignments_with_status && classroom.assignments_with_status.length > 0 && (
                    <div className="mb-3 flex-grow">
                      <h6 className="text-white-80 mb-2 text-base">Class Assignments:</h6>
                      <ul className="list-none mb-0 text-sm">
                        {classroom.assignments_with_status.map((assignmentInfo: AssignmentInfo) => (
                          <li key={assignmentInfo.assignment.id} className="flex justify-between items-center py-2 border-b border-gray-700 last:border-b-0">
                            <span className="text-white-75 truncate mr-2">
                              <i className="fas fa-book-open mr-1 text-white-70"></i>
                              {assignmentInfo.assignment.title}
                            </span>
                            {assignmentInfo.status === 'Active' ? (
                              <a href={`/student/classroom/${classroom.id}/assignment/${assignmentInfo.assignment.id}`} className="bg-gradient-purple hover:from-purple-700 hover:to-indigo-800 text-white text-xs font-bold py-1.5 px-3 rounded-lg flex-shrink-0">
                                View Assignment
                              </a>
                            ) : (
                              <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                assignmentInfo.status === 'Submitted' ? 'bg-green-500' : 
                                assignmentInfo.status === 'Expired' ? 'bg-red-500' : 
                                'bg-gray-500'
                              } flex-shrink-0`}>
                                {assignmentInfo.status}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {classroom.materials_count > 0 && (
                    <div className="mb-3">
                      <h6 className="text-white-80 mb-2 text-base">Class Materials:</h6>
                      <p className="text-white-75 text-sm">This classroom has {classroom.materials_count} learning materials.</p>
                      <a href={`/student/classroom/${classroom.id}/materials`} className="border border-white-75 text-white-75 text-sm px-3 py-2 rounded-lg w-full text-center mt-2 hover:bg-white hover:text-dark-bg transition-colors duration-200">
                        View All Materials
                      </a>
                    </div>
                  )}

                  {aiQuizAwards[classroom.id] && Object.keys(aiQuizAwards[classroom.id]).length > 0 && (
                    <div className="mb-3">
                      <h6 className="text-white-80 mb-2 text-base">AI Quiz Awards:</h6>
                      <ul className="list-none mb-0 text-sm">
                        {Object.values(aiQuizAwards[classroom.id]).map((award, index) => (
                          <li key={index} className="flex justify-between items-center py-2 border-b border-gray-700 last:border-b-0">
                            <span className="text-white-75 truncate mr-2">
                              <i className="fas fa-award mr-1 text-white-70"></i>
                              {award.material_title} - Score: {award.score}
                            </span>
                            {award.award === 'gold' && <i className="fas fa-medal text-gold ml-2"></i>}
                            {award.award === 'silver' && <i className="fas fa-medal text-silver ml-2"></i>}
                            {award.award === 'bronze' && <i className="fas fa-medal text-bronze ml-2"></i>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-blue-100 text-blue-800 p-4 rounded-lg text-center">
          You are not enrolled in any classrooms yet. Join one using the invitation code!
        </div>
      )}

      {/* Join Classroom Modal */}
      <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50 hidden" id="joinClassroomModal" tabIndex={-1} aria-labelledby="joinClassroomModalLabel" aria-hidden="true">
        <div className="relative w-full max-w-md mx-auto">
          <div className="bg-dark-bg text-white rounded-2xl shadow-xl overflow-hidden">
            <div className="bg-gradient-blue p-4 flex justify-between items-center">
              <h5 className="text-white text-lg font-semibold" id="joinClassroomModalLabel">Join New Classroom</h5>
              <button type="button" className="text-white hover:text-gray-200" data-bs-dismiss="modal" aria-label="Close">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-4">
              {joinClassroomError && <div className="bg-red-500 bg-opacity-20 text-red-100 p-2 rounded-lg mb-3">{joinClassroomError}</div>}
              {joinClassroomSuccess && <div className="bg-green-500 bg-opacity-20 text-green-100 p-2 rounded-lg mb-3">{joinClassroomSuccess}</div>}
              <form onSubmit={handleJoinClassroom}>
                <div className="mb-3">
                  <label htmlFor="invitationCode" className="block text-white text-sm font-bold mb-2">Invitation Code</label>
                  <input
                    type="text"
                    className="shadow appearance-none border rounded w-full py-2 px-3 bg-dark-bg text-white leading-tight focus:outline-none focus:shadow-outline border-gray-600"
                    id="invitationCode"
                    value={invitationCode}
                    onChange={(e) => setInvitationCode(e.target.value)}
                    placeholder="Enter invitation code"
                    required
                  />
                </div>
                <div className="flex justify-end space-x-2">
                  <button type="button" className="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded-lg" data-bs-dismiss="modal">Close</button>
                  <button type="submit" className="bg-gradient-blue hover:from-blue-600 hover:to-teal-600 text-white font-bold py-2 px-4 rounded-lg">Join</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StudentDashboard; 