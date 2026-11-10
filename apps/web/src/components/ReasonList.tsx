import { actionLink, type ActionDestinations, type ReasonItem } from '../lib/readinessCatalog';

export default function ReasonList({
  items,
  canAdmin,
  to,
}: {
  items: ReasonItem[];
  canAdmin: boolean;
  to: ActionDestinations;
}) {
  return (
    <ul>
      {items.map((item, index) => {
        const link = actionLink(item, canAdmin, to);
        return (
          <li key={(item.subject || '') + ':' + (item.code || item.diagnostic || index)}>
            {item.subject ? item.subject + ': ' : ''}
            {item.text} <small>{item.fixerLabel}.</small>
            {item.diagnostic && (
              <>
                <br />
                <small>Diagnostic code: {item.diagnostic}</small>
              </>
            )}
            <br />
            <a href={link.href}>{link.label}</a>
          </li>
        );
      })}
    </ul>
  );
}
