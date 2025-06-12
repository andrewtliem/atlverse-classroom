import { supabase } from './supabase';

export async function signIn(email: string, password: string) {
  const { data, error } = await supabase.auth.signInWithPassword({
    email: email,
    password: password,
  });

  if (error) {
    throw error;
  }
  return data;
}

export async function signUp(email: string, password: string, firstName: string, lastName: string, role: 'student' | 'teacher') {
  // Supabase 'auth.signUp' allows custom data to be stored in the 'user_metadata' column
  const { data, error } = await supabase.auth.signUp({
    email: email,
    password: password,
    options: {
      data: {
        first_name: firstName,
        last_name: lastName,
        role: role,
      },
    },
  });

  if (error) {
    throw error;
  }
  return data;
}

export async function signOut() {
  const { error } = await supabase.auth.signOut();
  if (error) {
    throw error;
  }
}

export async function getCurrentUser() {
  const { data: { session }, error } = await supabase.auth.getSession();
  if (error) {
    throw error;
  }
  return session?.user || null;
}

export function listenToAuthChanges(callback: (event: string, session: any | null) => void) {
    const { data: { subscription: authListener } } = supabase.auth.onAuthStateChange((event, session) => {
        callback(event, session);
    });
    return authListener;
} 