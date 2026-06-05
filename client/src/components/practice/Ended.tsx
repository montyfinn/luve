/** Brief "reviewing your conversation" confirmation between live and analysis.
 *  (Cat/Lottie deferred — CSS spinner stand-in.) */
export function Ended() {
  return (
    <div className="p-view p-main">
      <div className="p-wrap p-center">
        <div className="p-ended">
          <div className="p-spinner p-spinner--sm" style={{ margin: "0 auto" }} />
          <h2>Nice work.</h2>
          <p>We're reviewing your conversation…</p>
        </div>
      </div>
    </div>
  );
}
