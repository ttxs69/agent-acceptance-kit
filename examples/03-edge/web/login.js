// 登录页对接。这个文件没有门覆盖 —— 03-edge 要抓的就是这一点。
export function submit(form) {
  return fetch("/api/login", {method: "POST", body: JSON.stringify(form)});
}
