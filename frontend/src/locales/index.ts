import type { LangCode } from '@/stores/locale'
import zh from './zh'
import en from './en'

// CC reserved terms: TOE, SFR, OSP, ST, CC, PP, SPD, AI etc. keep in English
// Translate UI text only

export interface Messages {
  nav: {
    riskDashboard: string
    toeManage: string
    threatManage: string
    securityManage: string
    testManage: string
    exportST: string
    aiModels: string
    userManage: string
    settings: string
  }
  settings: {
    title: string
    language: string
    languageDesc: string
    saved: string
    aiModels: string
    userManage: string
    systemSettings: string
    languageNames: Record<string, string>
    pdfParseTimeout: string
    pdfParseTimeoutDesc: string
    settingsSaved: string
    stTemplate: string
    stTemplateDesc: string
    stTemplateSaveToFile: string
    stTemplateLoadFromFile: string
    stTemplatePlaceholders: string
    // Log tab
    logs?: string
    logAudit?: string
    logErrors?: string
    logFilterUsername?: string
    logFilterMethod?: string
    logFilterResource?: string
    logFilterStatus?: string
    logFilterErrorType?: string
    logFilterLevel?: string
    logClearOld?: string
    logConfirmClear?: string
    logErrorDetail?: string
    logColTime?: string
    logColUser?: string
    logColMethod?: string
    logColPath?: string
    logColStatus?: string
    logColIp?: string
    logColDuration?: string
    logColErrorType?: string
    logColLevel?: string
    logColMessage?: string
    logColStack?: string
    [key: string]: any
  }
  common: {
    logout: string
    save: string
    cancel: string
    delete: string
    edit: string
    add: string
    confirm: string
    confirmDelete: string
    success: string
    error: string
    loading: string
    noData: string
    actions: string
    search: string
    reset: string
    export: string
    import: string
    refresh: string
    create: string
    update: string
    view: string
    name: string
    description: string
    status: string
    required: string
    createdAt: string
    updatedAt: string
    remarks: string
    aiGenerate: string
    selectAtLeast: string
    [key: string]: any
  }
  login: {
    title: string
    username: string
    password: string
    rememberMe: string
    loginBtn: string
    forgotPassword: string
    loginSuccess: string
    loginFailed: string
    subtitle?: string
    mustChangePwdTitle?: string
    mustChangePwdDesc?: string
    mustChangePwdNew?: string
    mustChangePwdConfirm?: string
    mustChangePwdMismatch?: string
    mustChangePwdTooShort?: string
    mustChangePwdSame?: string
    mustChangePwdSuccess?: string
    [key: string]: any
  }
  layout: {
    welcome: string
  }
  user: {
    title: string
    addUser: string
    editUser: string
    username: string
    password: string
    role: string
    admin: string
    normalUser: string
    changePassword: string
    toeAccess: string
    manageToeAccess: string
    selectToeAccess: string
    toeReadOnly: string
    toeReadWrite: string
    allToes: string
    [key: string]: any
  }
  aiModel: {
    title: string
    addModel: string
    editModel: string
    configName: string
    apiBaseUrl: string
    apiKey: string
    modelName: string
    timeout: string
    timeoutDesc: string
    workingModel: string
    setAsWorking: string
    inUse: string
    verify: string
    verified: string
    notVerified: string
    verifySuccess: string
    verifyFailed: string
    chat: string
    send: string
    thinking: string
    startChat: string
    clearChat: string
    inputPlaceholder: string
    noModels: string
    leaveBlankToKeep: string
  }
  toe: Record<string, any>
  threat: Record<string, any>
  security: Record<string, any>
  test: Record<string, any>
  risk: Record<string, any>
  exportSt: Record<string, any>
}

const messages: Record<LangCode, Messages> = {
  zh: zh as Messages,
  en: en as Messages,
}

export function getMessages(lang: LangCode): Messages {
  return messages[lang] ?? messages.en
}

export function getLangNames(): Record<string, string> {
  return { zh: '中文(简体)', en: 'English' }
}

export default messages
