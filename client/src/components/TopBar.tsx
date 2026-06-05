import { GearIcon } from "./icons";

interface TopBarProps {
  /** show health + user + sign out (true once "signed in", i.e. on the practice view) */
  showSession: boolean;
  userName: string;
  userInitial: string;
  onSignOut: () => void;
  onOpenDiagnostics: () => void;
}

/** Persistent top bar (brand + health chip + user + diagnostics entry). */
export function TopBar({ showSession, userName, userInitial, onSignOut, onOpenDiagnostics }: TopBarProps) {
  return (
    <div className="p-top">
      <div className="p-brand">
        L<b>U</b>VE
      </div>
      <div className="p-top__right">
        {showSession && (
          <span className="p-chip p-chip--ok">
            <span className="d" />
            Ready
          </span>
        )}
        {showSession && (
          <div className="p-user">
            <span>{userName}</span>
            <span className="p-avatar">{userInitial}</span>
          </div>
        )}
        {showSession && (
          <button className="p-linkbtn" onClick={onSignOut}>
            Sign out
          </button>
        )}
        <button className="p-iconbtn" aria-label="Developer diagnostics" onClick={onOpenDiagnostics}>
          <GearIcon size={17} />
        </button>
      </div>
    </div>
  );
}
