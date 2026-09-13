import './library.css';
import { ChevronRight, FolderIcon } from './icons';
import { LABELS } from '../lib/labels';
import { folderBreadcrumbs, type FolderNode } from '../lib/folders';

interface FolderBreadcrumbsProps {
  /** The folder currently being browsed. `''` is the root. */
  folder: string;
  onNavigate: (folder: string) => void;
}

/**
 * THE FOLDER TRAIL.
 *
 * THE ROOT CRUMB IS AUTHORED HERE AND NOT BY `folderBreadcrumbs`, deliberately:
 * what the top of the trail is CALLED ("All experiments") is a product decision,
 * not a fact derivable from a path, so the pure function returns nothing for it
 * and this component supplies the word.
 *
 * IT IS A `nav` WITH AN `ol`, which is what a breadcrumb is, and the current
 * folder is `aria-current="page"` rather than a link. Making the last crumb a
 * button that navigates to where you already are is a control that does nothing.
 *
 * AND IT RENDERS EVEN AT THE ROOT — one crumb, not zero. A trail that appears
 * only once you are inside something gives a reader no way to learn that folders
 * exist at all, and no stable place to look for where they are.
 */
export function FolderBreadcrumbs({ folder, onNavigate }: FolderBreadcrumbsProps) {
  const crumbs = folderBreadcrumbs(folder);
  return (
    <nav className="library-breadcrumbs" aria-label="Folder path">
      <ol className="library-crumbs">
        <li className="library-crumb">
          {folder === '' ? (
            <span className="library-crumb-current" aria-current="page">
              {LABELS.libraryRootFolder}
            </span>
          ) : (
            <button
              type="button"
              className="library-crumb-link"
              onClick={() => onNavigate('')}
            >
              {LABELS.libraryRootFolder}
            </button>
          )}
        </li>
        {crumbs.map((crumb, i) => {
          const isLast = i === crumbs.length - 1;
          return (
            <li className="library-crumb" key={crumb.path}>
              <ChevronRight
                className="library-crumb-sep"
                size={13}
                strokeWidth={2}
                aria-hidden="true"
              />
              {isLast ? (
                <span className="library-crumb-current" aria-current="page">
                  {crumb.name}
                </span>
              ) : (
                <button
                  type="button"
                  className="library-crumb-link"
                  onClick={() => onNavigate(crumb.path)}
                >
                  {crumb.name}
                </button>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

interface FolderListProps {
  /**
   * The immediate child folders of the folder being browsed.
   *
   * NAMED `folders` AND NOT `children`, deliberately. `children` is React's own
   * slot for nested JSX, and a component that takes an ARRAY OF DATA under that
   * name reads at every call site as though markup were being passed in.
   */
  folders: FolderNode[];
  onNavigate: (folder: string) => void;
  /** True at the root, where the model note is worth stating once. */
  showModelNote: boolean;
}

/**
 * THE SUBFOLDERS OF THE FOLDER BEING BROWSED — and nothing else.
 *
 * **THERE IS NO "NEW FOLDER" CONTROL HERE, AND THAT IS THE MODEL RATHER THAN AN
 * OMISSION.** A folder path comes into existence because an experiment is filed
 * under it; there is no folder entity to create. A `+ New folder` button would
 * either do nothing until something was moved into it, or create a thing this
 * build cannot store — and `CLAUDE.md` §15 forbids shipping UI that implies a
 * capability the build does not have. The way to make a folder is to type its
 * path when creating or moving an experiment, which is where the control is.
 *
 * There is likewise NO rename and NO delete. Renaming a path means rewriting
 * every member as N independent writes with no transaction around them, so
 * half-renamed is reachable; deleting is what moving the last member out already
 * does. Neither is offered.
 *
 * EACH ROW SHOWS THE SUBTREE TOTAL, NOT THE DIRECT COUNT. A folder whose own rows
 * are all one level deeper would read `0` otherwise, which a reader would
 * correctly interpret as empty — and an empty folder is a thing this model says
 * cannot exist.
 */
export function FolderList({ folders, onNavigate, showModelNote }: FolderListProps) {
  if (folders.length === 0) return null;
  return (
    <section className="library-folders" aria-labelledby="library-folders-heading">
      <h2 className="library-folders-heading" id="library-folders-heading">
        {LABELS.libraryFoldersHeading}
      </h2>
      {/*
        STATED ONCE, AT THE ROOT. Every reader arrives expecting Drive, and four of
        Drive's behaviours are absent here. Saying what a folder IS conveys that
        without listing four capabilities we do not have — which is the difference
        between a truthful screen and a changelog of absences.
      */}
      {showModelNote && (
        <p className="library-folders-note">{LABELS.libraryFolderModelNote}</p>
      )}
      <ul className="library-folder-list">
        {folders.map((node) => (
          <li key={node.path}>
            <button
              type="button"
              className="library-folder"
              onClick={() => onNavigate(node.path)}
            >
              <FolderIcon
                className="library-folder-icon"
                size={16}
                strokeWidth={1.75}
                aria-hidden="true"
              />
              <span className="library-folder-name">{node.name}</span>
              <span className="library-folder-count">
                {node.totalCount}
                <span className="sr-only">
                  {' '}
                  experiment{node.totalCount === 1 ? '' : 's'} in this folder and below
                </span>
              </span>
              <ChevronRight
                className="library-folder-chevron"
                size={16}
                strokeWidth={2}
                aria-hidden="true"
              />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
