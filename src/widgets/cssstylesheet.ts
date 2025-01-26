// Copyright (c) ipylab contributors
// Distributed under the terms of the Modified BSD License.

import { IpylabModel } from './ipylab';

/**
 * The model for a CSSStyleSheet.
 */
export class CSSStyleSheetModel extends IpylabModel {
  /**
   * The default attributes.
   */
  defaults(): Backbone.ObjectHash {
    return {
      ...super.defaults(),
      _model_name: 'CSSStyleSheetModel'
    };
  }

  async ipylabInit() {
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, this.sheet];
    await super.ipylabInit(this.sheet);
  }

  close(comm_closed?: boolean): Promise<void> {
    document.adoptedStyleSheets = document.adoptedStyleSheets.filter(
      item => item !== this.sheet
    );
    return super.close(comm_closed);
  }

  async operation(op: string, payload: any): Promise<any> {
    switch (op) {
      case 'deleteRule':
        this.sheet.deleteRule(payload.index);
        return this._listCSSRules();
      case 'insertRule':
        this.sheet.insertRule(payload.rule, payload.index);
        return this._listCSSRules();
      case 'replace':
        await this.sheet.replace(payload.text);
        return this._listCSSRules();
      case 'listCSSRules':
        return this._listCSSRules();
      default:
        return await super.operation(op, payload);
    }
  }

  /**
   * Return the text of the css rules.
   */
  _listCSSRules(): string[] {
    const rules = [];
    for (const rule of this.sheet.cssRules) {
      rules.push(rule.cssText);
    }
    return rules;
  }

  /**
   * Set global css variables.
   */
  setVariables(variables: any) {
    for (const name in variables) {
      document.documentElement.style.setProperty(name, variables[name]);
    }
    const list: Record<string, string> = {};
    const allVariables = this.listVariables();
    for (const name in variables) {
      list[name] = allVariables[name];
    }
    return list;
  }

  /**
   * Geta list of the global css variables.
   */
  listVariables(): Record<string, string> {
    const list: Record<string, string> = {};

    if ('computedStyleMap' in document.documentElement) {
      // Chrome
      const styles = (document.documentElement as any).computedStyleMap();
      styles.forEach((val: any, key: string) => {
        if (key.startsWith('--')) {
          list[key] = val.toString();
        }
      });
    } else {
      // Firefox
      const styles = getComputedStyle(document.documentElement);
      for (let i = 0; i < styles.length; i++) {
        const propertyName = styles[i]!;
        if (propertyName.startsWith('--')) {
          const value = styles.getPropertyValue(propertyName);
          list[propertyName] = value;
        }
      }
    }
    return list;
  }

  sheet = new CSSStyleSheet();
  readonly base: CSSStyleSheet;
}
