import { useState, useEffect } from 'react';
import api from '../services/api-client';

export function useQuery<T = any>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setIsLoading(true);
    api.get(path).then(res => {
      setData(res.data);
      setIsLoading(false);
    }).catch(() => {
      setIsLoading(false);
    });
  }, [path]);

  return { data, isLoading };
}