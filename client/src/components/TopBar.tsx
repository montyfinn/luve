import { useState } from "react";
import { CatSleepLuveLogo, ClaudeCat } from "./ClaudeCat";
import { GearIcon, HistoryIcon } from "./icons";

interface TopBarProps {
  /** show health + user + sign out (true once "signed in", i.e. on the practice view) */
  showSession: boolean;
  userName: string;
  userInitial: string;
  onSignOut: () => void;
  showHistory?: boolean;
  onOpenHistory?: () => void;
  onOpenDiagnostics: () => void;
}

/** Persistent top bar (brand + health chip + user + diagnostics entry). */
export function TopBar({
  showSession,
  userName,
  userInitial,
  onSignOut,
  showHistory = false,
  onOpenHistory,
  onOpenDiagnostics,
}: TopBarProps) {
  const [signOutHelp, setSignOutHelp] = useState(false);

  const handleSignOut = () => {
    setSignOutHelp(false);
    onSignOut();
  };

  return (
    <div className="p-top">
      <div className="p-brand" aria-label="LUVE">
        <CatSleepLuveLogo width={158} height={158} className="p-brand-cat" />
        <span className="p-brand-word" aria-hidden="true">
          L<b>U</b>VE
        </span>
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
          <span
            className="p-signout-wrap"
            onMouseEnter={() => setSignOutHelp(true)}
            onMouseLeave={() => setSignOutHelp(false)}
            onFocus={() => setSignOutHelp(true)}
            onBlur={() => setSignOutHelp(false)}
          >
            <button className="p-linkbtn" onClick={handleSignOut}>
              Sign out
            </button>
            {signOutHelp && <ClaudeCat width={74} height={74} className="p-signout-cat" />}
          </span>
        )}
        {showSession && showHistory && onOpenHistory && (
          <button className="p-iconbtn" aria-label="Past sessions" onClick={onOpenHistory}>
            <HistoryIcon size={17} />
          </button>
        )}
        <button className="p-iconbtn" aria-label="Developer diagnostics" onClick={onOpenDiagnostics}>
          <GearIcon size={17} />
        </button>
      </div>
    </div>
  );
}
