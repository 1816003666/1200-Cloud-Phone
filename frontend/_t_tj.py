p = r"C:\Users\熏香花朵凛然绽放\Desktop\1200台云手机部署\cloud-phone-board\cloud-phone-board\frontend\src\views\Tasks.jsx"
src = open(p, encoding="utf-8").read()

# 1) form 初始加 cron_expr
old = "  const [form, setForm] = useState({\n    name: '', action: 'health_check', schedule_type: 'interval', interval_seconds: 86400,\n  })"
new = "  const [form, setForm] = useState({\n    name: '', action: 'health_check', schedule_type: 'interval', interval_seconds: 86400, cron_expr: '',\n  })"
assert old in src; src = src.replace(old, new)

# 2) select 加 cron option + cron 输入框
old = """        <select value={form.schedule_type} onChange={(e) => update('schedule_type', e.target.value)}>
          <option value="once">单次</option>
          <option value="interval">周期</option>
        </select>
        {form.schedule_type === 'interval' && (
          <select value={form.interval_seconds} onChange={(e) => update('interval_seconds', Number(e.target.value))}>
            <option value={3600}>每 1 小时</option>
            <option value={21600}>每 6 小时</option>
            <option value={43200}>每 12 小时</option>
            <option value={86400}>每天</option>
            <option value={604800}>每周</option>
          </select>
        )}"""
new = """        <select value={form.schedule_type} onChange={(e) => update('schedule_type', e.target.value)}>
          <option value="once">单次</option>
          <option value="interval">周期</option>
          <option value="cron">Cron</option>
        </select>
        {form.schedule_type === 'interval' && (
          <select value={form.interval_seconds} onChange={(e) => update('interval_seconds', Number(e.target.value))}>
            <option value={3600}>每 1 小时</option>
            <option value={21600}>每 6 小时</option>
            <option value={43200}>每 12 小时</option>
            <option value={86400}>每天</option>
            <option value={604800}>每周</option>
          </select>
        )}
        {form.schedule_type === 'cron' && (
          <input
            placeholder="cron 表达式，如 0 2 * * *"
            value={form.cron_expr || ''}
            onChange={(e) => update('cron_expr', e.target.value)}
            style={{ width: 190 }}
          />
        )}"""
assert old in src; src = src.replace(old, new)

# 3) 提交时传 cron_expr
old = """      await api.createTask({
        ...form,
        params: {}, device_ids: [],
        interval_seconds: Number(form.interval_seconds),
      })"""
new = """      await api.createTask({
        ...form,
        params: {}, device_ids: [],
        interval_seconds: Number(form.interval_seconds),
        cron_expr: form.cron_expr || '',
      })"""
assert old in src; src = src.replace(old, new)

# 4) 重置表单时带 cron_expr
old = "setForm({ ...form, name: '' })"
new = "setForm({ ...form, name: '', cron_expr: '' })"
assert old in src; src = src.replace(old, new)

# 5) 类型列显示
old = "                <td>{t.schedule_type === 'once' ? '单次' : '周期'}</td>"
new = "                <td>{t.schedule_type === 'once' ? '单次' : t.schedule_type === 'cron' ? `Cron: ${t.cron_expr || ''}` : '周期'}</td>"
assert old in src; src = src.replace(old, new)

open(p, "w", encoding="utf-8").write(src)
print("Tasks.jsx cron ok")
