
interface Env {
  DB: D1Database;
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  try {
    const sql  = await request.text();
    
    // プレースホルダー `?` と `.bind()` を使用
    const result = await env.DB.prepare(sql).run();

    if (result.meta.changes > 0 ) {
      return new Response(JSON.stringify(
        { message: "SQLs送信成功",
          executeSql: sql
        }
      ), { status: 201 });
    }
    
    return new Response(JSON.stringify(
      { message: "SQL送信失敗",
        executeSql: sql
      }), { status: 500 });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), { status: 500 });
  }
};

