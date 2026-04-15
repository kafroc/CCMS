import request from './request'

export interface TaskResult {
  id: string
  task_type: string
  status: 'pending' | 'running' | 'done' | 'failed'
  progress_message: string | null
  result_summary: string | null
  error_message: string | null
  download_url: string | null
}

export const taskApi = {
  get(taskId: string) {
    return request.get<any, { code: number; data: TaskResult }>(`/tasks/${taskId}`)
  },
}
