type Data = Record<string, any>;

export function decisionReviewView(data: Data, symbol: string, online: boolean, now = Date.now()) {
 const review = data?.strategies?.reviews?.[symbol];
 const age = review?.evaluated_at ? (now - Date.parse(review.evaluated_at)) / 1000 : Infinity;
 const fresh = online && Number.isFinite(age) && age >= 0 && age <= 120;
 const errors = ["error", "selector_error", "data_error", "quote_error", "entry_error", "exit_error"]
  .some(key => Boolean(data?.engine?.[key]));
 const session = data?.engine?.session;
 const checks = Object.values(review?.checks || {}) as Data[];
 const roles = Object.values(review?.agents || {}) as Data[];
 let stance = "WAIT";
 if (!online) stance = "OFFLINE";
 else if (!fresh) stance = "AWAITING REVIEW";
 else if (errors) stance = "BLOCKED";
 else if (data?.account?.open_positions > 0) stance = "MANAGING";
 else if (session === "ENTRY_WINDOW" && review?.phase === "CANDIDATE" && checks.length > 0 &&
          checks.every(check => check.status === "PASS") && ["CALL", "PUT"].includes(review?.decision)) stance = review.decision;
 return { review, fresh, stance, checks, passed: checks.filter(check => check.status === "PASS").length,
  evaluated: fresh ? roles.filter(role => !["NOT_EVALUATED", "PENDING", "POST_TRADE"].includes(role.status)).length : 0,
  total: roles.length || 14,
  reason: !online ? "Disconnected; recorded evidence only" : !fresh ? "No current coordinator review" : errors ? "Engine reports an error; inspect current status" : review?.reason };
}
