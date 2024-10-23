// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.
import { Signal } from '@lumino/signaling';

/**
 * Clean a dotted name prior to passing to one of these functions.
 *
 * @param subpath A dotted name
 * @returns
 */
function cleanSubpath(subpath: string) {
  return (subpath || '').replace('[', '.').replace(']', '');
}

/**
 * Get a nested property relative to `obj` using the `subpath` notation.
 * @param obj The starting object.
 * @param subpath The subpath to the property.
 */
export function getNestedProperty({
  obj,
  subpath,
  nullIfMissing = false,
  basename = ''
}: {
  obj: object;
  subpath: string;
  nullIfMissing?: boolean;
  basename?: string;
}): any {
  subpath = cleanSubpath(subpath);
  let subpath_ = '';
  const parts = subpath.split('.');
  let pname = '';
  for (let i = 0; i < parts.length; i++) {
    pname = parts[i];
    if (pname in obj) {
      obj = obj[pname as keyof typeof obj];
      subpath_ = !subpath_ ? pname : `${subpath_}.${pname}`;
    } else {
      break;
    }
  }
  if (subpath_ !== subpath || typeof obj === 'undefined') {
    if (nullIfMissing) {
      return null;
    }
    if (obj instanceof Array && !isNaN(+pname)) {
      throw new Error(
        `Index ${subpath_}[${pname}] out of range for ` +
          `Array (${obj.length}) {${toJSONsubstituteCylic(obj)}}`
      );
    }
    basename = basename ? basename + '.' : basename;
    throw new Error(`Property "${basename}${pname}" not found!`);
  }
  return obj;
}

/**
 * Set a nested property at `subpath` relative to the obj on `obj`.
 *
 * @param obj The object
 * @param subpath The dotted path of the property to set
 * @param value The value to set as the property
 */
export function setNestedProperty({
  obj,
  subpath,
  value,
  basename = ''
}: {
  obj: object;
  subpath: string;
  value: any;
  basename?: string;
}) {
  subpath = cleanSubpath(subpath);
  const objname = subpath.split('.').slice(0, -1).join('.');
  const key = subpath.split('.').slice(-1)[0];
  obj = getNestedProperty({ obj, subpath: objname, basename });
  (obj as any)[key] = value;
}

/**
 * Update the property. Equivalent to python: `dict.update`.
 */
export async function updateProperty({
  obj,
  subpath,
  value,
  basename = ''
}: {
  obj: object;
  subpath: string;
  value: any;
  basename?: string;
}): Promise<null> {
  obj = getNestedProperty({ obj, subpath, basename });
  return Object.assign(obj, value);
}

/**
 * Convert a string definition of a function to a function object.
 * @param code The function as a string: eg. 'function (a, b) { return a + b; }'
 * @returns
 */
export function toFunction(code: string) {
  return new Function('return ' + code)();
}

/**
 * Provide an object detailing objects in obj.
 *
 * omitHidden: Will omit properties starting with '_'
 *
 * @param obj Any object.
 * @returns
 */
function findAllProperties({
  obj: obj,
  items = [],
  type = '',
  depth = 1,
  omitHidden = false
}: {
  obj: any;
  items?: Array<string>;
  type?: string;
  depth?: number;
  omitHidden?: boolean;
}): Array<string> {
  if (!obj || depth === 0) {
    return [...new Set(items)];
  }

  const props = Object.getOwnPropertyNames(obj).filter(value =>
    omitHidden ? value.slice(0, 1) !== '_' : true
  );
  return findAllProperties({
    obj: Object.getPrototypeOf(obj),
    items: [...items, ...props],
    type,
    depth: depth - 1,
    omitHidden: omitHidden
  });
}

/**
 * Returns a mapping of types and names for obj.
 *
 * This function is cyclic ref safe so is suitable for converting to json.
 * @param obj Any object
 */
export function listProperties({
  obj,
  type = '',
  depth = 1,
  omitHidden = false
}: {
  obj: any;
  type?: string;
  depth?: number;
  omitHidden?: boolean;
}): any {
  const out: any = {};
  for (const name of findAllProperties({
    obj,
    items: [],
    type,
    depth,
    omitHidden
  })) {
    const obj_ = obj[name];
    let type_: string = typeof obj_;
    let val: any = name;
    /*eslint no-fallthrough: ["error", { "commentPattern": "break[\\s\\w]*omitted" }]*/
    switch (type_) {
      case 'string':
      case 'number':
      case 'bigint':
      case 'boolean':
        out[name] = obj_;
        break;
      case 'undefined':
        out[name] = null;
        break;
      case 'object':
        if (obj_ instanceof Promise) {
          type_ = 'Promise';
          break;
        } else if (obj_ instanceof Signal) {
          type_ = 'Signal';
        }
        if (depth > 1) {
          val = {};
          val[name] = listProperties({
            obj: obj_,
            type,
            depth: 1,
            omitHidden
          });
        }
      // caution: break is omitted intentionally
      default:
        if (!out[`<${type_}s>`]) {
          out[`<${type_}s>`] = [val];
        } else {
          out[`<${type_}s>`].push(val);
          out[`<${type_}s>`] = out[`<${type_}s>`].sort();
        }
    }
  }
  // Sort alphabetically
  return Object.fromEntries(Object.entries(out).sort());
}

/**
 * Execute a method at subpath of obj.
 *
 * Args are used in the method.
 */
export async function executeMethod({
  obj,
  subpath,
  args,
  basename = ''
}: {
  obj: object;
  subpath: string;
  args: any[];
  basename?: string;
}): Promise<any> {
  if (!subpath) {
    throw new Error('subpath required!');
  }
  subpath = cleanSubpath(subpath);
  const ownername = subpath.split('.').slice(0, -1).join('.');
  const owner = getNestedProperty({ obj, subpath: ownername, basename });
  let func = getNestedProperty({ obj, subpath, basename });
  func = func.bind(owner, ...args);
  return await func();
}

/**
 * Modify the object to make it usable as an IObservableDisposable.
 * @param obj The object to modify.
 * @returns
 */
export function ensureObservableDisposable(obj: any) {
  if (typeof obj !== 'object') {
    throw new Error(`An object is required but got ${typeof obj} `);
  }
  if (obj.disposed) {
    // The presence of obj.disposed likely means obj provides
    // an IObservableDisposable interface.
    return;
  }
  if (!obj.dispose) {
    Object.defineProperties(obj, {
      dispose: { value: () => null as any, enumerable: false },
      ipylabDisposeOnClose: { value: true, enumerable: false }
    });
  }
  const disposed = new Signal<any, null>(obj);
  const dispose_ = obj.dispose.bind(obj);
  const dispose = () => {
    if (obj.isDisposed) {
      return;
    }
    dispose_();
    disposed.emit(null);
    Signal.clearData(obj);
    if (!obj.isDisposed) {
      obj.isDisposed = true;
    }
  };
  Object.defineProperties(obj, {
    dispose: {
      value: dispose.bind(obj),
      enumerable: false,
      configurable: true,
      writable: false
    },
    disposed: {
      value: disposed,
      writable: true,
      enumerable: false
    }
  });
}

/**
 * Convert content replacing cyclic objects with a list of its properties.
 * @param value Content represent JSON
 * @returns
 */
export function toJSONsubstituteCylic(value: any) {
  try {
    return JSON.stringify(value);
  } catch {
    // Assuming the error is due to circular reference
    return JSON.stringify(value, _replacer);
  }
}

function _replacer(key: string, value: any) {
  // Filtering out properties
  if (typeof value !== 'object') {
    return value;
  }
  try {
    JSON.stringify(value);
    return value;
  } catch {
    const out = listProperties({
      obj: value,
      omitHidden: true,
      depth: 3
    });
    out['WARNING'] =
      'This is a simplified representation because it contains circular references.';
    return out;
  }
}
