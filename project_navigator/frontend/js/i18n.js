let _lang = 'en';
try {
  const stored = localStorage.getItem('pnav_lang');
  if (stored) { _lang = stored; }
  else { _lang = navigator.language.startsWith('zh') ? 'zh-CN' : 'en'; }
} catch (_) {}

const _msg = {
  en: {
    'app.title': 'Project Navigator',
    'auth.signin': 'Sign in',
    'auth.signin_to': 'Sign in to your account.',
    'auth.register': 'Create account',
    'auth.register_to': 'Create a new account.',
    'auth.new_here': 'New here?',
    'auth.already': 'Already have an account?',
    'auth.signin_instead': 'Sign in instead',
    'auth.create': 'Create an account',
    'auth.failed': 'Sign-in failed.',
    'auth.username': 'Username',
    'auth.password': 'Password',

    'sidebar.projects': 'Projects',
    'sidebar.new_project': '+ New project',
    'sidebar.collapse': 'Collapse sidebar',
    'sidebar.no_projects': 'No projects yet.',
    'sidebar.project_name': 'Project name\u2026',

    'project.none': '(no project)',
    'project.create': 'Create',
    'project.cancel': 'Cancel',
    'project.rename': 'Rename project',
    'project.delete': 'Delete project',
    'project.delete_confirm': 'Delete project "{name}" and all its content?',
    'project.no_selected': 'No project selected. Use the sidebar to',
    'project.select_hint': '+ New project',

    'goal.title': 'Ultimate goal',
    'goal.ph': 'Click to set your north star\u2026',
    'goal.input_ph': 'State your goal in one clear sentence\u2026',
    'goal.save': 'Save',
    'goal.cancel': 'Cancel',

    'stage.add': '+ Add stage',
    'stage.new': 'New stage',
    'stage.name_ph': 'Stage name\u2026',
    'stage.empty': 'No stages yet.',
    'stage.empty_hint': 'Add your first stage to get started.',
    'stage.delete': 'Delete stage',
    'stage.delete_confirm': 'Delete this stage and all its content?',

    'bq.header': '⊘ Blockers & questions',
    'bq.add_ph': 'Add a blocker or question\u2026',
    'bq.add': 'Add',
    'bq.none': 'No blockers or questions.',
    'bq.too_deep': 'Too deep',

    'sub.ph': 'Add a sub-item\u2026',
    'sub.none': 'No sub-items.',
    'sub.add': 'Add',

    'idea.header': '✦ Ideas & thinking',
    'idea.ph': 'Log an idea or thought\u2026',
    'idea.add': 'Add',
    'idea.none': 'No ideas noted yet.',

    'status.todo': 'To Do',
    'status.active': 'Active',
    'status.blocked': 'Blocked',
    'status.done': 'Done',
    'status.park': 'Park',
    'status.review': 'Review',
    'status.nice': 'Nice to have',
    'status.solve': 'To Solve \u2192normal',
    'status.to_do': '\u25CB To do',
    'status.is_active': '\u25CF Active',
    'status.is_blocked': '\u2298 Blocked',
    'status.is_done': '\u2713 Done',
    'status.is_park': '\u2691 Parked',
    'status.is_review': '\u25D0 Review',
    'status.is_nice': '\u2726 Nice to have',

    'deep.back': '\u21A9 Back to normal',
    'deep.go': '\u2691 Going too deep?',

    'user.switch': 'Switch user\u2026',
    'user.switch_to': 'Switch to\u2026',
    'user.account': 'account',
    'user.back': '\u2190 Back',

    'header.theme': 'Theme',
    'header.light': '\u2600 Light',
    'header.dark': '\u263E Dark',
  },
  'zh-CN': {
    'app.title': 'Project Navigator',
    'auth.signin': '登录',
    'auth.signin_to': '登录您的账户。',
    'auth.register': '创建账户',
    'auth.register_to': '创建一个新账户。',
    'auth.new_here': '新用户？',
    'auth.already': '已有账户？',
    'auth.signin_instead': '改为登录',
    'auth.create': '创建账户',
    'auth.failed': '登录失败。',
    'auth.username': '用户名',
    'auth.password': '密码',

    'sidebar.projects': '项目',
    'sidebar.new_project': '+ 新建项目',
    'sidebar.collapse': '收起侧栏',
    'sidebar.no_projects': '暂无项目。',
    'sidebar.project_name': '项目名称\u2026',

    'project.none': '（无项目）',
    'project.create': '创建',
    'project.cancel': '取消',
    'project.rename': '重命名项目',
    'project.delete': '删除项目',
    'project.delete_confirm': '删除项目"{name}"及其所有内容？',
    'project.no_selected': '未选择项目。使用侧栏',
    'project.select_hint': '+ 新建项目',

    'goal.title': '终极目标',
    'goal.ph': '点击设定您的北极星\u2026',
    'goal.input_ph': '用一句话陈述您的目标\u2026',
    'goal.save': '保存',
    'goal.cancel': '取消',

    'stage.add': '+ 添加阶段',
    'stage.new': '新阶段',
    'stage.name_ph': '阶段名称\u2026',
    'stage.empty': '暂无阶段。',
    'stage.empty_hint': '添加第一个阶段开始使用。',
    'stage.delete': '删除阶段',
    'stage.delete_confirm': '删除此阶段及其所有内容？',

    'bq.header': '⊘ 阻碍与问题',
    'bq.add_ph': '添加阻碍或问题\u2026',
    'bq.add': '添加',
    'bq.none': '暂无阻碍或问题。',
    'bq.too_deep': '太深入了',

    'sub.ph': '添加子项\u2026',
    'sub.none': '暂无子项。',
    'sub.add': '添加',

    'idea.header': '✦ 想法与思考',
    'idea.ph': '记录想法\u2026',
    'idea.add': '添加',
    'idea.none': '暂无想法。',

    'status.todo': '待办',
    'status.active': '进行中',
    'status.blocked': '受阻',
    'status.done': '完成',
    'status.park': '搁置',
    'status.review': '审查中',
    'status.nice': '锦上添花',
    'status.solve': '已解决 →普通',
    'status.to_do': '○ 待办',
    'status.is_active': '● 进行中',
    'status.is_blocked': '⊘ 受阻',
    'status.is_done': '✓ 完成',
    'status.is_park': '⚑ 已搁置',
    'status.is_review': '◐ 审查中',
    'status.is_nice': '✦ 锦上添花',

    'deep.back': '↩ 返回普通',
    'deep.go': '⚑ 太深入了？',

    'user.switch': '切换用户…',
    'user.switch_to': '切换到…',
    'user.account': '账户',
    'user.back': '← 返回',

    'header.theme': '主题',
    'header.light': '☀ 浅色',
    'header.dark': '☾ 深色',
  },
};

export function t(key, fallback) {
  const v = _msg[_lang] && _msg[_lang][key];
  return v != null ? v : (fallback != null ? fallback : key);
}

export function getLang() { return _lang; }

export function setLang(code) {
  if (_msg[code]) {
    _lang = code;
    try { localStorage.setItem('pnav_lang', code); } catch (_) {}
  }
}

export function applyI18n(root) {
  if (!root) root = document;
  root.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    el.textContent = t(key, el.textContent);
  });
  root.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.dataset.i18nPlaceholder;
    el.placeholder = t(key, el.placeholder);
  });
}
