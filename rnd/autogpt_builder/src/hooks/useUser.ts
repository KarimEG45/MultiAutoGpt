import { User } from "@supabase/supabase-js";
import { useEffect, useState } from "react";
import useSupabase from "./useSupabase";

const useUser = () => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const supabase = useSupabase();

  if (!supabase) {
    return { user: null, isLoading: false, error: 'Failed to create Supabase client' };
  }

  useEffect(() => {
    const fetchUser = async () => {
      setIsLoading(true);
      const { data, error } = await supabase.auth.getUser();
      if (data) {
        setUser(data.user);
      } else if (error) {
        setError(error.message);
      }
      setIsLoading(false);
    };

    fetchUser();

    // Listen for changes in authentication state
    const { data: authListener } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_IN') {
        fetchUser();
      } else if (event === 'SIGNED_OUT') {
        setUser(null);
        setError(null);
      }
    });

    return () => {
      authListener.subscription.unsubscribe();
    };
  }, []);

  return { user, isLoading, error };
};

export default useUser;
